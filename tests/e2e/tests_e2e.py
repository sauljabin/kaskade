import asyncio
import json
import struct
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import httpx
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka.schema_registry.protobuf import ProtobufSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from fastavro import schemaless_writer
from google.protobuf.descriptor_pb2 import (
    FieldDescriptorProto,
    FileDescriptorProto,
    FileDescriptorSet,
)
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass
from testcontainers.community.kafka import KafkaContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import HttpWaitStrategy
from textual.widgets import DataTable

from kaskade.admin import KaskadeAdmin
from kaskade.configs import (
    APICURIO,
    APICURIO_OPTION,
    AUTO_OFFSET_RESET,
    BOOTSTRAP_SERVERS,
    EARLIEST,
)
from kaskade.consumer import KaskadeConsumer, ListRecords
from kaskade.deserializers import Deserialization
from kaskade.models import PartitionOffset, PartitionSelection

MY_VALUE = "my-value"
MY_KEY = "my-key"
MY_TOPIC = "my-topic"


def sandbox_version(name: str) -> str:
    prefix = f"{name}="
    env_path = Path(__file__).resolve().parents[2] / "sandbox" / ".env"
    value = next(
        (
            line.removeprefix(prefix)
            for line in env_path.read_text().splitlines()
            if line.startswith(prefix)
        ),
        "",
    )
    if not value:
        raise RuntimeError(f"Missing {name} in {env_path}")
    return value


CONFLUENT_VERSION = sandbox_version("CONFLUENT_VERSION")
KAFKA_IMAGE = f"confluentinc/cp-kafka:{CONFLUENT_VERSION}"
SCHEMA_REGISTRY_IMAGE = f"confluentinc/cp-schema-registry:{CONFLUENT_VERSION}"
SCHEMA_REGISTRY_PORT = 8081
APICURIO_VERSION = sandbox_version("APICURIO_VERSION")
APICURIO_IMAGE = f"apicurio/apicurio-registry:{APICURIO_VERSION}"
APICURIO_PORT = 8080
JSON_TOPIC = "json-schema"
AVRO_TOPIC = "avro-schema"
PROTOBUF_TOPIC = "protobuf-schema"
AVRO_SCHEMA = json.dumps(
    {
        "type": "record",
        "name": "User",
        "fields": [{"name": "name", "type": "string"}],
    }
)
JSON_SCHEMA = json.dumps(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "User",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
)
PROTOBUF_SCHEMA = 'syntax = "proto3"; message User { string name = 1; }'


def protobuf_user_model() -> tuple[FileDescriptorProto, type[Message]]:
    descriptor = FileDescriptorProto(name="user.proto", syntax="proto3")
    user_descriptor = descriptor.message_type.add(name="User")
    user_descriptor.field.add(
        name="name",
        number=1,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
        type=FieldDescriptorProto.TYPE_STRING,
    )
    pool = DescriptorPool()
    pool.Add(descriptor)
    return descriptor, GetMessageClass(pool.FindMessageTypeByName("User"))


PROTOBUF_DESCRIPTOR, ProtobufUser = protobuf_user_model()


def kafka_container() -> KafkaContainer:
    return KafkaContainer(KAFKA_IMAGE).with_kraft()


def schema_registry_container(network: Network) -> DockerContainer:
    wait_strategy = HttpWaitStrategy(SCHEMA_REGISTRY_PORT, "/subjects")
    wait_strategy.with_startup_timeout(60)
    return (
        DockerContainer(SCHEMA_REGISTRY_IMAGE)
        .with_network(network)
        .with_network_aliases("schema-registry")
        .with_exposed_ports(SCHEMA_REGISTRY_PORT)
        .with_env("SCHEMA_REGISTRY_HOST_NAME", "schema-registry")
        .with_env("SCHEMA_REGISTRY_LISTENERS", f"http://0.0.0.0:{SCHEMA_REGISTRY_PORT}")
        .with_env("SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS", "PLAINTEXT://kafka:9092")
        .with_env("SCHEMA_REGISTRY_KAFKASTORE_TOPIC_REPLICATION_FACTOR", "1")
        .waiting_for(wait_strategy)
    )


def schema_registry_url(container: DockerContainer) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(SCHEMA_REGISTRY_PORT)
    return f"http://{host}:{port}"


def apicurio_container() -> DockerContainer:
    wait_strategy = HttpWaitStrategy(APICURIO_PORT, "/apis/registry/v3/system/info")
    wait_strategy.with_startup_timeout(60)
    return (
        DockerContainer(APICURIO_IMAGE)
        .with_exposed_ports(APICURIO_PORT)
        .with_env("QUARKUS_HTTP_PORT", str(APICURIO_PORT))
        .waiting_for(wait_strategy)
    )


def apicurio_url(container: DockerContainer) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(APICURIO_PORT)
    return f"http://{host}:{port}/apis/registry/v3"


def register_apicurio_schema(url: str, artifact: str, artifact_type: str, content: str) -> int:
    response = httpx.post(
        f"{url}/groups/default/artifacts",
        json={
            "artifactId": artifact,
            "artifactType": artifact_type,
            "firstVersion": {
                "content": {
                    "content": content,
                    "contentType": (
                        "text/plain" if artifact_type == "PROTOBUF" else "application/json"
                    ),
                }
            },
        },
    )
    response.raise_for_status()
    body = response.json()
    return int(body.get("version", body)["contentId"])


def apicurio_type_ref(name: str) -> bytes:
    encoded = name.encode()
    message = b"\x0a" + bytes([len(encoded)]) + encoded
    return bytes([len(message)]) + message


def apicurio_frame(artifact_id: int, payload: bytes) -> bytes:
    return struct.pack(">bI", 0, artifact_id) + payload


def create_topic(config, topic: str = MY_TOPIC, partitions: int = 1):
    admin_client = AdminClient(config)
    futures = admin_client.create_topics(
        [NewTopic(topic, num_partitions=partitions, replication_factor=1)]
    ).values()
    for future in futures:
        future.result()


def populate_topic(config):
    producer = Producer(config)
    producer.produce(MY_TOPIC, key=MY_KEY, value=MY_VALUE)
    producer.flush()


class TestE2E(unittest.IsolatedAsyncioTestCase):
    async def wait_for_rows(self, table: DataTable, expected: int, timeout: float = 15) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while len(table.rows) != expected:
            if loop.time() >= deadline:
                self.fail(f"Expected {expected} row(s), found {len(table.rows)}")
            await asyncio.sleep(0.1)

    async def assert_consumed_user(
        self,
        topic: str,
        kafka_config: dict,
        value_deserialization: Deserialization,
        *,
        registry_config: dict[str, str] | None = None,
        protobuf_config: dict[str, str] | None = None,
        avro_config: dict[str, str] | None = None,
        json_config: dict[str, str] | None = None,
        expected_registry_provider: str | None = None,
    ) -> None:
        consumer_app = KaskadeConsumer(
            topic,
            kafka_config | {AUTO_OFFSET_RESET: EARLIEST},
            registry_config or {},
            protobuf_config or {},
            avro_config or {},
            Deserialization.STRING,
            value_deserialization,
            json_config=json_config,
        )
        async with consumer_app.run_test():
            table = consumer_app.query_one(DataTable)
            await self.wait_for_rows(table, 1)
            first_row = table.get_row("0/0")
            self.assertEqual(MY_KEY, first_row[0])
            records = consumer_app.query_one(ListRecords).records
            record = next(iter(records.values())) if records else None
            self.assertEqual(
                "{'name': 'Ada'}",
                first_row[1],
                record.dict() if record else None,
            )
            if expected_registry_provider is not None:
                assert record is not None
                schema = record.dict()["value"].get("schema")
                self.assertIsNotNone(schema, record.dict())
                self.assertEqual(expected_registry_provider, schema["provider"])
                self.assertEqual("default", schema["group"])
                self.assertEqual(f"{topic}-value", schema["artifact"])

    async def test_admin(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config)

            admin_app = KaskadeAdmin(config)
            async with admin_app.run_test():
                table = admin_app.query_one(DataTable)
                await self.wait_for_rows(table, 1)

                self.assertEqual(MY_TOPIC, table.get_row(MY_TOPIC)[0])

    async def test_consumer(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config)
            populate_topic(config)

            consumer_app = KaskadeConsumer(
                MY_TOPIC,
                config | {AUTO_OFFSET_RESET: EARLIEST},
                {},
                {},
                {},
                Deserialization.STRING,
                Deserialization.STRING,
            )
            async with consumer_app.run_test():
                table = consumer_app.query_one(DataTable)
                await self.wait_for_rows(table, 1)

                first_row = table.get_row("0/0")
                self.assertEqual(MY_KEY, first_row[0])
                self.assertEqual(MY_VALUE, first_row[1])

    async def test_consumer_assigns_only_explicit_partition(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config, partitions=2)
            producer = Producer(config)
            producer.produce(MY_TOPIC, key="ignored", value="partition-0", partition=0)
            producer.produce(MY_TOPIC, key="selected", value="partition-1", partition=1)
            producer.flush()

            consumer_app = KaskadeConsumer(
                MY_TOPIC,
                config,
                {},
                {},
                {},
                Deserialization.STRING,
                Deserialization.STRING,
                partitions=(PartitionSelection(1, PartitionOffset.EARLIEST),),
            )
            async with consumer_app.run_test():
                table = consumer_app.query_one(DataTable)
                await self.wait_for_rows(table, 1)

                selected_row = table.get_row("1/0")
                self.assertEqual("selected", selected_row[0])
                self.assertEqual("partition-1", selected_row[1])

    async def test_consumer_deserializes_registry_and_confluent_framing_formats(self):
        with Network() as network, tempfile.TemporaryDirectory() as directory:
            avro_path = Path(directory) / "user.avsc"
            avro_path.write_text(AVRO_SCHEMA, encoding="utf-8")
            descriptor_path = Path(directory) / "user.desc"
            descriptor_set = FileDescriptorSet(file=[PROTOBUF_DESCRIPTOR])
            descriptor_path.write_bytes(descriptor_set.SerializeToString())
            kafka_container_instance = (
                kafka_container().with_network(network).with_network_aliases("kafka")
            )
            with (
                kafka_container_instance as kafka,
                schema_registry_container(network) as registry,
            ):
                kafka_config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
                registry_config = {"url": schema_registry_url(registry)}
                registry_client = SchemaRegistryClient(registry_config)
                cases = (
                    (JSON_TOPIC, JSONSerializer(JSON_SCHEMA, registry_client), {"name": "Ada"}),
                    (AVRO_TOPIC, AvroSerializer(registry_client, AVRO_SCHEMA), {"name": "Ada"}),
                    (
                        PROTOBUF_TOPIC,
                        ProtobufSerializer(ProtobufUser, registry_client),
                        ProtobufUser(name="Ada"),
                    ),
                )
                producer = Producer(kafka_config)
                for topic, serializer, value in cases:
                    create_topic(kafka_config, topic)
                    context = SerializationContext(topic, MessageField.VALUE)
                    producer.produce(topic, key=MY_KEY, value=serializer(value, context))
                producer.flush()

                for topic, _, _ in cases:
                    with self.subTest(topic=topic):
                        await self.assert_consumed_user(
                            topic,
                            kafka_config,
                            Deserialization.REGISTRY,
                            registry_config=registry_config,
                        )

                confluent_framing_cases = (
                    (
                        JSON_TOPIC,
                        Deserialization.JSON,
                        {"json_config": {"framing": "confluent"}},
                    ),
                    (
                        AVRO_TOPIC,
                        Deserialization.AVRO,
                        {
                            "avro_config": {
                                "value": str(avro_path),
                                "framing": "confluent",
                            }
                        },
                    ),
                    (
                        PROTOBUF_TOPIC,
                        Deserialization.PROTOBUF,
                        {
                            "protobuf_config": {
                                "descriptor": str(descriptor_path),
                                "value": "User",
                                "framing": "confluent",
                            }
                        },
                    ),
                )
                for topic, deserialization, configs in confluent_framing_cases:
                    with self.subTest(topic=topic, framing="confluent"):
                        await self.assert_consumed_user(
                            topic,
                            kafka_config,
                            deserialization,
                            **configs,
                        )

    async def test_consumer_deserializes_native_apicurio_formats(self):
        with kafka_container() as kafka, apicurio_container() as registry:
            kafka_config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            registry_url = apicurio_url(registry)
            json_id = register_apicurio_schema(
                registry_url, f"{JSON_TOPIC}-value", "JSON", JSON_SCHEMA
            )
            avro_id = register_apicurio_schema(
                registry_url, f"{AVRO_TOPIC}-value", "AVRO", AVRO_SCHEMA
            )
            protobuf_id = register_apicurio_schema(
                registry_url, f"{PROTOBUF_TOPIC}-value", "PROTOBUF", PROTOBUF_SCHEMA
            )
            avro_payload = BytesIO()
            schemaless_writer(avro_payload, json.loads(AVRO_SCHEMA), {"name": "Ada"})
            cases = (
                (
                    JSON_TOPIC,
                    apicurio_frame(json_id, b'{"name":"Ada"}'),
                ),
                (AVRO_TOPIC, apicurio_frame(avro_id, avro_payload.getvalue())),
                (
                    PROTOBUF_TOPIC,
                    apicurio_frame(
                        protobuf_id,
                        apicurio_type_ref("User") + ProtobufUser(name="Ada").SerializeToString(),
                    ),
                ),
            )
            producer = Producer(kafka_config)
            for topic, payload in cases:
                create_topic(kafka_config, topic)
                producer.produce(topic, key=MY_KEY, value=payload)
            producer.flush()

            registry_config = {
                "provider": APICURIO_OPTION,
                "apicurio.registry.url": registry_url,
            }
            for topic, _ in cases:
                with self.subTest(topic=topic):
                    await self.assert_consumed_user(
                        topic,
                        kafka_config,
                        Deserialization.REGISTRY,
                        registry_config=registry_config,
                        expected_registry_provider=APICURIO,
                    )

            with tempfile.TemporaryDirectory() as directory:
                avro_path = Path(directory) / "user.avsc"
                avro_path.write_text(AVRO_SCHEMA, encoding="utf-8")
                descriptor_path = Path(directory) / "user.desc"
                descriptor_set = FileDescriptorSet(file=[PROTOBUF_DESCRIPTOR])
                descriptor_path.write_bytes(descriptor_set.SerializeToString())
                local_cases = (
                    (
                        JSON_TOPIC,
                        Deserialization.JSON,
                        {"json_config": {"framing": "apicurio"}},
                    ),
                    (
                        AVRO_TOPIC,
                        Deserialization.AVRO,
                        {
                            "avro_config": {
                                "value": str(avro_path),
                                "framing": "apicurio",
                            }
                        },
                    ),
                    (
                        PROTOBUF_TOPIC,
                        Deserialization.PROTOBUF,
                        {
                            "protobuf_config": {
                                "descriptor": str(descriptor_path),
                                "value": "User",
                                "framing": "apicurio",
                            }
                        },
                    ),
                )
                for topic, deserialization, configs in local_cases:
                    with self.subTest(topic=topic, framing="apicurio"):
                        await self.assert_consumed_user(
                            topic,
                            kafka_config,
                            deserialization,
                            **configs,
                        )


if __name__ == "__main__":
    unittest.main()
