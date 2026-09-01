import os
import time
import uuid
from collections.abc import Callable
from functools import partial
from pathlib import Path
from time import sleep
from typing import Any

import click
from confluent_kafka import KafkaError, KafkaException, Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka.schema_registry.protobuf import ProtobufSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from faker import Faker
from rich.console import Console
from rich.status import Status

from kaskade.authentication import configure_aws_msk_iam
from kaskade.cli_utils import tuple_properties_to_dict, validate_aws_config
from kaskade.configs import AWS_CONFIGS, BOOTSTRAP_SERVERS, MIN_INSYNC_REPLICAS_CONFIG
from kaskade.utils import file_to_str, pack_bytes, py_to_avro
from sandbox.avro_model.user import User as AvroUser
from sandbox.json_model.user import User as JsonUser
from sandbox.protobuf_model.user_pb2 import User as ProtobufUser

SANDBOX_PATH = Path(__file__).resolve().parent
JSON_USER_SCHEMA = str(SANDBOX_PATH / "json_model" / "user.schema.json")
AVRO_USER_SCHEMA = str(SANDBOX_PATH / "avro_model" / "user.avsc")
ERRORS_TOPIC = "errors"
ERROR_CASES = ("key", "value", "both", "valid")
MALFORMED_KEY_CASES = frozenset({"key", "both"})
MALFORMED_VALUE_CASES = frozenset({"value", "both"})
MALFORMED_PAYLOAD_BYTES = 32


class Populator:
    def __init__(
        self,
        kafka_config: dict[str, Any],
        partitions: int = 10,
        replication_factor: int | None = None,
        min_insync_replicas: int | None = None,
    ) -> None:
        self.producer = Producer(
            kafka_config
            | {
                "client.id": f"{uuid.uuid4()}",
            }
        )
        self.admin_client = AdminClient(kafka_config)
        self.partitions = partitions
        self.replication_factor = replication_factor
        self.min_insync_replicas = min_insync_replicas

    def create_topic(self, topic: str) -> None:
        topic_config = {}
        if self.min_insync_replicas is not None:
            topic_config[MIN_INSYNC_REPLICAS_CONFIG] = str(self.min_insync_replicas)

        new_topic = NewTopic(
            topic=topic,
            num_partitions=self.partitions,
            replication_factor=(
                self.replication_factor if self.replication_factor is not None else -1
            ),
            config=topic_config,
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
                    raise

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

    def populate_registry_errors(
        self,
        serializer: JSONSerializer,
        faker: Faker,
        total_messages: int,
    ) -> None:
        for n in range(total_messages):
            error_case = ERROR_CASES[n % len(ERROR_CASES)]
            key = serializer(
                JsonUser(name=faker.name()),
                SerializationContext(ERRORS_TOPIC, MessageField.KEY),
            )
            value = serializer(
                JsonUser(name=faker.name()),
                SerializationContext(ERRORS_TOPIC, MessageField.VALUE),
            )
            if error_case in MALFORMED_KEY_CASES:
                key = self._malformed_payload()
            if error_case in MALFORMED_VALUE_CASES:
                value = self._malformed_payload()
            self.producer.produce(
                ERRORS_TOPIC,
                key=key,
                value=value,
                headers=[("sandbox-error-case", error_case.encode("utf-8"))],
            )
        self.producer.flush(5)

    @staticmethod
    def _malformed_payload() -> bytes:
        return b"\xff" + os.urandom(MALFORMED_PAYLOAD_BYTES - 1)


def run_population(
    console: Console,
    status: Status,
    populator: Populator,
    topic: str,
    action: Callable[[], None],
) -> None:
    start = time.time()
    status.update(f" [yellow]populating topic:[/] {topic}")
    populator.create_topic(topic)
    action()
    console.print(f":white_check_mark: {topic} [green]{time.time() - start:.1f} secs[/]")


def sandbox_kafka_config(bootstrap_servers: str, aws_config: dict[str, str]) -> dict[str, Any]:
    validate_aws_config(aws_config)
    return configure_aws_msk_iam({BOOTSTRAP_SERVERS: bootstrap_servers}, aws_config)


@click.command()
@click.option("--messages", default=1000, help="Number of messages to send.")
@click.option(
    "--partitions",
    type=click.IntRange(min=1),
    default=10,
    help="Number of partitions for created topics.",
    show_default=True,
)
@click.option(
    "--replication-factor",
    type=click.IntRange(min=1),
    default=None,
    help="Replication factor for created topics. Uses the broker default when omitted.",
)
@click.option(
    "--min-insync-replicas",
    type=click.IntRange(min=1),
    default=None,
    help="Minimum in-sync replicas for created topics. Uses the broker default when omitted.",
)
@click.option(
    "--bootstrap-servers", default="localhost:19092", help="Bootstrap servers.", show_default=True
)
@click.option(
    "--registry",
    default="http://localhost:18081",
    help="Schema registry. For Apicurio use 'http://localhost:18082/apis/ccompat/v7'",
    show_default=True,
)
@click.option(
    "--aws",
    "aws_config",
    help=f"Amazon MSK IAM property. Multiple are allowed. Valid properties: {AWS_CONFIGS}.",
    metavar="property=value",
    multiple=True,
    callback=tuple_properties_to_dict,
)
def main(
    messages: int,
    partitions: int,
    replication_factor: int | None,
    min_insync_replicas: int | None,
    bootstrap_servers: str,
    registry: str,
    aws_config: dict[str, str],
) -> None:
    kafka_config = sandbox_kafka_config(bootstrap_servers, aws_config)
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
    populator = Populator(
        kafka_config,
        partitions=partitions,
        replication_factor=replication_factor,
        min_insync_replicas=min_insync_replicas,
    )
    console = Console()
    with console.status("", spinner="dots") as status:
        for topic, generator, serializer in topics:
            run_population(
                console,
                status,
                populator,
                topic,
                partial(populator.populate, topic, generator, serializer, messages),
            )

        run_population(
            console,
            status,
            populator,
            ERRORS_TOPIC,
            partial(populator.populate_registry_errors, json_serializer, faker, messages),
        )


if __name__ == "__main__":
    main()
