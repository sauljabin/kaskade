import time
from time import sleep

from confluent_kafka.cimpl import NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka.schema_registry.protobuf import ProtobufSerializer
from confluent_kafka.serialization import SerializationContext, MessageField
from typing import Callable, Any
import uuid

import click
from kaskade.configs import BOOTSTRAP_SERVERS, MIN_INSYNC_REPLICAS_CONFIG
from rich.console import Console
from confluent_kafka.admin import AdminClient
from confluent_kafka import Producer, KafkaError, KafkaException
from faker import Faker

from kaskade.utils import pack_bytes, file_to_str, py_to_avro
from tests.protobuf_model.user_pb2 import User as ProtobufUser
from tests.avro_model.user import User as AvroUser
from tests.json_model.user import User as JsonUser

JSON_USER_SCHEMA = "tests/json_model/user.schema.json"
AVRO_USER_SCHEMA = "tests/avro_model/user.avsc"


class Populator:
    def __init__(self, kafka_config: dict[str, str]) -> None:
        self.producer = Producer(
            kafka_config
            | {
                "client.id": f"{uuid.uuid4()}",
            }
        )
        self.admin_client = AdminClient(kafka_config)

    def create_topic(self, topic: str) -> None:
        new_topic = NewTopic(
            topic=topic,
            num_partitions=10,
            replication_factor=3,
            config={
                MIN_INSYNC_REPLICAS_CONFIG: 2,
            },
        )
        futures = self.admin_client.create_topics([new_topic])
        for future in futures.values():
            try:
                future.result()
                sleep(0.1)
            except KafkaException as ke:
                if (
                    len(ke.args) > 0
                    and hasattr(ke.args[0], "code")
                    and ke.args[0].code() is not KafkaError.TOPIC_ALREADY_EXISTS
                ):
                    raise ke

    def populate(
        self,
        topic: str,
        generator: Callable[[], Any],
        serializer: Callable[[Any], Any],
        total_messages: int,
    ) -> None:
        for n in range(total_messages):
            value = generator()
            self.producer.produce(topic, value=serializer(value), key=f"{value}")
        self.producer.flush(5)


@click.command()
@click.option("--messages", default=1000, help="Number of messages to send.")
@click.option(
    "--bootstrap-servers", default="localhost:19092", help="Bootstrap servers.", show_default=True
)
@click.option(
    "--registry",
    default="http://localhost:18081",
    help="Schema registry. For Apicurio registry use 'http://localhost:18081/apis/ccompat/v7'",
    show_default=True,
)
def main(messages: int, bootstrap_servers: str, registry: str) -> None:
    registry_client = SchemaRegistryClient({"url": registry})
    avro_serializer = AvroSerializer(
        registry_client,
        file_to_str(AVRO_USER_SCHEMA),
        lambda value, ctx: vars(value),
    )
    json_serializer = JSONSerializer(
        file_to_str(JSON_USER_SCHEMA),
        registry_client,
        lambda value, ctx: vars(value),
    )
    protobuf_serializer = ProtobufSerializer(
        ProtobufUser, registry_client, {"use.deprecated.format": False}
    )
    faker = Faker()
    topics = [
        (
            "string",
            lambda: faker.name(),
            lambda value: value.encode("utf-8"),
        ),
        (
            "integer",
            lambda: faker.pyint(min_value=500, max_value=10000),
            lambda value: pack_bytes(">i", value),
        ),
        (
            "long",
            lambda: faker.pyint(min_value=500, max_value=10000),
            lambda value: pack_bytes(">q", value),
        ),
        (
            "float",
            lambda: faker.pyfloat(min_value=500, max_value=10000),
            lambda value: pack_bytes(">f", value),
        ),
        (
            "double",
            lambda: faker.pyfloat(min_value=500, max_value=10000),
            lambda value: pack_bytes(">d", value),
        ),
        (
            "boolean",
            lambda: faker.pybool(),
            lambda value: pack_bytes(">?", value),
        ),
        (
            "null",
            lambda: "not null" if faker.pybool() else None,
            lambda value: value.encode("utf-8") if value else None,
        ),
        (
            "json",
            lambda: faker.json(),
            lambda value: value.encode("utf-8"),
        ),
        (
            "json-schema",
            lambda: JsonUser(name=faker.name()),
            lambda value: json_serializer(
                value, SerializationContext("json-schema", MessageField.VALUE)
            ),
        ),
        (
            "protobuf",
            lambda: ProtobufUser(name=faker.name()),
            lambda value: value.SerializeToString(),
        ),
        (
            "protobuf-schema",
            lambda: ProtobufUser(name=faker.name()),
            lambda value: protobuf_serializer(
                value, SerializationContext("protobuf-schema", MessageField.VALUE)
            ),
        ),
        (
            "avro",
            lambda: AvroUser(name=faker.name()),
            lambda value: py_to_avro(AVRO_USER_SCHEMA, vars(value)),
        ),
        (
            "avro-schema",
            lambda: AvroUser(name=faker.name()),
            lambda value: avro_serializer(
                value, SerializationContext("avro-schema", MessageField.VALUE)
            ),
        ),
    ]
    populator = Populator({BOOTSTRAP_SERVERS: bootstrap_servers})
    console = Console()
    with console.status("", spinner="dots") as status:
        for topic, generator, serializer in topics:
            start = time.time()
            status.update(f" [yellow]populating topic:[/] {topic}")
            populator.create_topic(topic)
            populator.populate(topic, generator, serializer, messages)
            console.print(f":white_check_mark: {topic} [green]{time.time() - start:.1f} secs[/]")


if __name__ == "__main__":
    main()
