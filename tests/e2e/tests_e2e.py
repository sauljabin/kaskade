import asyncio
import json
import struct
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import httpx
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from confluent_kafka.schema_registry import Schema, SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.schema_registry.json_schema import JSONDeserializer, JSONSerializer
from confluent_kafka.schema_registry.protobuf import ProtobufDeserializer, ProtobufSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from fastavro import parse_schema, schemaless_writer
from google.protobuf.descriptor_pb2 import (
    FieldDescriptorProto,
    FileDescriptorProto,
    FileDescriptorSet,
)
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass
from testcontainers.community.kafka import KafkaContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import HttpWaitStrategy
from textual.widgets import Checkbox, DataTable, TextArea

from kaskade.admin import KaskadeAdmin
from kaskade.apicurio import ApicurioConfig
from kaskade.configs import (
    APICURIO,
    APICURIO_OPTION,
    AUTO_OFFSET_RESET,
    BOOTSTRAP_SERVERS,
    EARLIEST,
)
from kaskade.consumer import KaskadeConsumer, ListRecords
from kaskade.consumer_service import ConsumerSettings
from kaskade.deserializers import Deserialization
from kaskade.models import PartitionOffset, PartitionSelection
from kaskade.producer import KaskadeProducer, RecordComposer, RecordDraft
from kaskade.producer.source import DraftField
from kaskade.producer_service import ProducerSettings
from kaskade.serializers import Serialization

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


USER_WITH_ADDRESS = {"name": "Ada", "address": {"city": "Quito"}}


def write_schemas_with_references(directory: Path) -> None:
    """A user that references an address: an Avro named type and a Protobuf import."""
    address = {
        "type": "record",
        "name": "Address",
        "namespace": "shop",
        "fields": [{"name": "city", "type": "string"}],
    }
    user = {
        "type": "record",
        "name": "User",
        "namespace": "shop",
        "fields": [{"name": "name", "type": "string"}, {"name": "address", "type": "Address"}],
    }
    (directory / "shop.Address.avsc").write_text(json.dumps(address), encoding="utf-8")
    (directory / "user.avsc").write_text(json.dumps(user), encoding="utf-8")
    (directory / "common").mkdir()
    (directory / "common" / "address.proto").write_text(
        'syntax = "proto3"; package shop; message Address { string city = 1; }',
        encoding="utf-8",
    )
    (directory / "user.proto").write_text(
        'syntax = "proto3"; package shop; import "common/address.proto"; '
        'import "google/protobuf/timestamp.proto"; '
        "message User { string name = 1; Address address = 2; "
        "google.protobuf.Timestamp created = 3; }",
        encoding="utf-8",
    )


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


def apicurio_version_count(url: str, artifact: str) -> int:
    response = httpx.get(f"{url}/groups/default/artifacts/{quote(artifact, safe='')}/versions")
    response.raise_for_status()
    return int(response.json()["count"])


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


def consume_all(config, topic: str, expected: int) -> list:
    consumer = Consumer(config | {"group.id": "kaskade-e2e-verify", AUTO_OFFSET_RESET: EARLIEST})
    consumer.subscribe([topic])
    messages = []
    try:
        for _ in range(60):
            message = consumer.poll(0.5)
            if message is not None and message.error() is None:
                messages.append(message)
            if len(messages) == expected:
                break
    finally:
        consumer.close()
    return messages


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
            ConsumerSettings(
                topic,
                kafka_config | {AUTO_OFFSET_RESET: EARLIEST},
                Deserialization.STRING,
                value_deserialization,
                registry_config=registry_config or {},
                protobuf_config=protobuf_config or {},
                avro_config=avro_config or {},
                json_config=json_config,
            )
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

    async def wait_for_subtitle(self, composer: RecordComposer, text: str) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 30
        while text not in str(composer.frame.border_subtitle):
            if loop.time() >= deadline:
                self.fail(f"Expected {text!r}, found {composer.frame.border_subtitle!r}")
            await asyncio.sleep(0.1)

    async def test_producer_delivers_composed_records(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config, partitions=2)
            draft = RecordDraft(
                headers=(("trace", "a"), ("trace", None), ("empty", "")),
                key=DraftField("order-1", is_null=False),
                value=DraftField({"status": "paid"}, is_null=False),
            )
            producer_app = KaskadeProducer(
                ProducerSettings(
                    MY_TOPIC, config, value_serialization=Serialization.JSON, partition=1
                ),
                draft=draft,
            )
            async with producer_app.run_test() as pilot:
                composer = producer_app.query_one(RecordComposer)
                await pilot.pause()
                await pilot.press("ctrl+s")
                await self.wait_for_subtitle(composer, "Delivered · Partition 1 · Offset 0")
                producer_app.query_one("#key-null", Checkbox).value = True
                producer_app.query_one("#value-content", TextArea).load_text("{}")
                await pilot.pause()
                await pilot.press("ctrl+s")
                await self.wait_for_subtitle(composer, "Delivered · Partition 1 · Offset 1")

            first, second = sorted(consume_all(config, MY_TOPIC, 2), key=lambda m: m.offset())
            self.assertEqual(
                (1, b"order-1", b'{"status":"paid"}'),
                (first.partition(), first.key(), first.value()),
            )
            self.assertEqual([("trace", b"a"), ("trace", None), ("empty", b"")], first.headers())
            self.assertIsNone(second.key())
            self.assertEqual(b"{}", second.value())

    async def produce_user(
        self, topic: str, kafka_config: dict, value: dict | None = None, **serializers
    ) -> None:
        """Produce MY_KEY and a user, {"name": "Ada"} by default, with Kaskade's serializer."""
        draft = RecordDraft(
            key=DraftField(MY_KEY, is_null=False),
            value=DraftField(value or {"name": "Ada"}, is_null=False),
        )
        producer_app = KaskadeProducer(
            ProducerSettings(topic, kafka_config, **serializers), draft=draft
        )
        async with producer_app.run_test() as pilot:
            composer = producer_app.query_one(RecordComposer)
            await producer_app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("ctrl+s")
            await self.wait_for_subtitle(composer, "Delivered")

    async def test_producer_serializes_with_confluent_schema_registry(self):
        with Network() as network:
            kafka_container_instance = (
                kafka_container().with_network(network).with_network_aliases("kafka")
            )
            with (
                kafka_container_instance as kafka,
                schema_registry_container(network) as registry,
            ):
                kafka_config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
                registry_config = {"url": schema_registry_url(registry)}
                with SchemaRegistryClient(registry_config) as registry_client:
                    cases = (
                        (
                            JSON_TOPIC,
                            JSON_SCHEMA,
                            "JSON",
                            JSONDeserializer(JSON_SCHEMA, schema_registry_client=registry_client),
                        ),
                        (AVRO_TOPIC, AVRO_SCHEMA, "AVRO", AvroDeserializer(registry_client)),
                        (
                            PROTOBUF_TOPIC,
                            PROTOBUF_SCHEMA,
                            "PROTOBUF",
                            ProtobufDeserializer(ProtobufUser, {"use.deprecated.format": False}),
                        ),
                    )
                    for topic, schema, schema_type, official in cases:
                        with self.subTest(topic=topic):
                            create_topic(kafka_config, topic)
                            schema_id = registry_client.register_schema(
                                f"{topic}-value", Schema(schema, schema_type)
                            )
                            await self.produce_user(
                                topic,
                                kafka_config,
                                value_serialization=Serialization.REGISTRY,
                                registry_config=registry_config,
                            )

                            (message,) = consume_all(kafka_config, topic, 1)
                            self.assertEqual(struct.pack(">bI", 0, schema_id), message.value()[:5])
                            decoded = official(
                                message.value(), SerializationContext(topic, MessageField.VALUE)
                            )
                            if isinstance(decoded, Message):
                                decoded = MessageToDict(decoded)
                            self.assertEqual({"name": "Ada"}, decoded)
                            await self.assert_consumed_user(
                                topic,
                                kafka_config,
                                Deserialization.REGISTRY,
                                registry_config=registry_config,
                            )

    async def test_producer_serializes_with_native_apicurio(self):
        with kafka_container() as kafka, apicurio_container() as registry:
            kafka_config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            registry_url = apicurio_url(registry)
            registry_config = {"provider": APICURIO_OPTION, "apicurio.registry.url": registry_url}
            avro_payload = BytesIO()
            schemaless_writer(avro_payload, parse_schema(json.loads(AVRO_SCHEMA)), {"name": "Ada"})
            cases = (
                (JSON_TOPIC, "JSON", JSON_SCHEMA, b'{"name":"Ada"}'),
                (AVRO_TOPIC, "AVRO", AVRO_SCHEMA, avro_payload.getvalue()),
                (
                    PROTOBUF_TOPIC,
                    "PROTOBUF",
                    PROTOBUF_SCHEMA,
                    apicurio_type_ref("User") + ProtobufUser(name="Ada").SerializeToString(),
                ),
            )
            for topic, artifact_type, schema, payload in cases:
                with self.subTest(topic=topic):
                    create_topic(kafka_config, topic)
                    content_id = register_apicurio_schema(
                        registry_url, f"{topic}-value", artifact_type, schema
                    )
                    await self.produce_user(
                        topic,
                        kafka_config,
                        value_serialization=Serialization.REGISTRY,
                        registry_config=registry_config,
                        apicurio_config=ApicurioConfig.from_dict(registry_config),
                    )

                    (message,) = consume_all(kafka_config, topic, 1)
                    # The sandbox frames Apicurio records the same way.
                    self.assertEqual(apicurio_frame(content_id, payload), message.value())
                    await self.assert_consumed_user(
                        topic,
                        kafka_config,
                        Deserialization.REGISTRY,
                        registry_config=registry_config,
                        expected_registry_provider=APICURIO,
                    )

    async def consumed_values(self, topic: str, kafka_config: dict, registry_config: dict) -> list:
        consumer_app = KaskadeConsumer(
            ConsumerSettings(
                topic,
                kafka_config | {AUTO_OFFSET_RESET: EARLIEST},
                Deserialization.STRING,
                Deserialization.REGISTRY,
                registry_config=registry_config,
            )
        )
        async with consumer_app.run_test():
            await self.wait_for_rows(consumer_app.query_one(DataTable), 2)
            records = consumer_app.query_one(ListRecords).records.values()
            return [record.dict()["value"] for record in records]

    async def register_and_produce_twice(
        self,
        kafka_config: dict,
        registry_config: dict,
        registration: dict,
        directory: Path,
        **schema_files,
    ) -> list:
        """Produce USER_WITH_ADDRESS twice to registering topics; return each topic's values."""
        cases = (
            (AVRO_TOPIC, {"avro_config": {"value": str(directory / "user.avsc")}}),
            (
                PROTOBUF_TOPIC,
                {
                    "protobuf_config": {
                        "source": str(directory / "user.proto"),
                        "value": "shop.User",
                    }
                },
            ),
        )
        consumed = []
        for topic, files in cases:
            create_topic(kafka_config, topic)
            for _ in range(2):
                await self.produce_user(
                    topic,
                    kafka_config,
                    USER_WITH_ADDRESS,
                    value_serialization=Serialization.REGISTRY,
                    registry_config=registry_config | registration,
                    **schema_files,
                    **files,
                )
            consumed.append(await self.consumed_values(topic, kafka_config, registry_config))
        return consumed

    async def test_producer_registers_schemas_with_references_in_confluent(self):
        with Network() as network, tempfile.TemporaryDirectory() as directory:
            write_schemas_with_references(Path(directory))
            kafka_container_instance = (
                kafka_container().with_network(network).with_network_aliases("kafka")
            )
            with (
                kafka_container_instance as kafka,
                schema_registry_container(network) as registry,
            ):
                kafka_config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
                url = schema_registry_url(registry)
                consumed = await self.register_and_produce_twice(
                    kafka_config, {"url": url}, {"auto.register.schemas": "true"}, Path(directory)
                )

                for values in consumed:
                    self.assertEqual(
                        [USER_WITH_ADDRESS] * 2, [value["content"] for value in values]
                    )
                    self.assertEqual("CONFLUENT", values[0]["schema"]["provider"])
                with SchemaRegistryClient({"url": url}) as registry_client:
                    for subject in (
                        f"{AVRO_TOPIC}-value",
                        "shop.Address",
                        f"{PROTOBUF_TOPIC}-value",
                        "common/address.proto",
                    ):
                        with self.subTest(subject=subject):
                            self.assertEqual([1], registry_client.get_versions(subject))

    async def test_producer_registers_schemas_with_references_in_apicurio(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            kafka_container() as kafka,
            apicurio_container() as registry,
        ):
            write_schemas_with_references(Path(directory))
            kafka_config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            registry_url = apicurio_url(registry)
            registry_config = {"provider": APICURIO_OPTION, "apicurio.registry.url": registry_url}

            consumed = await self.register_and_produce_twice(
                kafka_config,
                registry_config,
                {"apicurio.registry.auto-register": "true"},
                Path(directory),
                apicurio_config=ApicurioConfig.from_dict(registry_config),
            )

            for values in consumed:
                self.assertEqual([USER_WITH_ADDRESS] * 2, [value["content"] for value in values])
                self.assertEqual("APICURIO", values[0]["schema"]["provider"])
            for artifact in (
                f"{AVRO_TOPIC}-value",
                "shop.Address",
                f"{PROTOBUF_TOPIC}-value",
                "common/address.proto",
            ):
                with self.subTest(artifact=artifact):
                    self.assertEqual(1, apicurio_version_count(registry_url, artifact))

    async def test_consumer(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config)
            populate_topic(config)

            consumer_app = KaskadeConsumer(
                ConsumerSettings(
                    MY_TOPIC,
                    config | {AUTO_OFFSET_RESET: EARLIEST},
                    Deserialization.STRING,
                    Deserialization.STRING,
                )
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
                ConsumerSettings(
                    MY_TOPIC,
                    config,
                    Deserialization.STRING,
                    Deserialization.STRING,
                    partitions=(PartitionSelection(1, PartitionOffset.EARLIEST),),
                )
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
                with SchemaRegistryClient(registry_config) as registry_client:
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
