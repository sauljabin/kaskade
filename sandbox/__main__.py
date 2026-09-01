import os
import time
import uuid
from collections.abc import Callable
from functools import partial
from pathlib import Path
from time import sleep
from typing import Any, cast

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
NULL_TOPIC = "null"
AVAILABLE_TOPICS = (
    "string",
    "integer",
    "long",
    "float",
    "double",
    "boolean",
    NULL_TOPIC,
    "json",
    "json-schema",
    "protobuf",
    "protobuf-schema",
    "avro",
    "avro-schema",
    ERRORS_TOPIC,
)
ERROR_CASES = ("key", "value", "both", "valid")
MALFORMED_KEY_CASES = frozenset({"key", "both"})
MALFORMED_VALUE_CASES = frozenset({"value", "both"})
MALFORMED_PAYLOAD_BYTES = 32
FAKE_NUMBER_MIN = 500
FAKE_NUMBER_MAX = 10000


def model_to_dict(value: Any, _: SerializationContext) -> dict[str, Any]:
    return cast(dict[str, Any], vars(value))


def fake_user(model: Callable[..., Any], faker: Faker) -> Any:
    return model(name=faker.name())


def serialize_with_context(
    value: Any,
    serializer: Callable[[Any, SerializationContext], Any],
    topic: str,
) -> Any:
    return serializer(value, SerializationContext(topic, MessageField.VALUE))


def serialize_protobuf(value: ProtobufUser) -> bytes:
    return value.SerializeToString()


def serialize_avro(value: AvroUser) -> bytes:
    return py_to_avro(AVRO_USER_SCHEMA, vars(value))


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
        for _ in range(total_messages):
            value = generator()
            self.producer.produce(topic, value=serializer(value), key=f"{value}")
        self.producer.flush(5)

    def populate_string(self, faker: Faker, total_messages: int) -> None:
        self.populate("string", faker.name, str.encode, total_messages)

    def populate_integer(self, faker: Faker, total_messages: int) -> None:
        self._populate_number("integer", faker.pyint, ">i", total_messages)

    def populate_long(self, faker: Faker, total_messages: int) -> None:
        self._populate_number("long", faker.pyint, ">q", total_messages)

    def populate_float(self, faker: Faker, total_messages: int) -> None:
        self._populate_number("float", faker.pyfloat, ">f", total_messages)

    def populate_double(self, faker: Faker, total_messages: int) -> None:
        self._populate_number("double", faker.pyfloat, ">d", total_messages)

    def _populate_number(
        self,
        topic: str,
        generator: Callable[..., Any],
        struct_format: str,
        total_messages: int,
    ) -> None:
        self.populate(
            topic,
            partial(generator, min_value=FAKE_NUMBER_MIN, max_value=FAKE_NUMBER_MAX),
            partial(pack_bytes, struct_format),
            total_messages,
        )

    def populate_boolean(self, faker: Faker, total_messages: int) -> None:
        self.populate("boolean", faker.pybool, partial(pack_bytes, ">?"), total_messages)

    def populate_null(self, total_messages: int) -> None:
        for _ in range(total_messages):
            self.producer.produce(NULL_TOPIC, key=None, value=None)
        self.producer.flush(5)

    def populate_json(self, faker: Faker, total_messages: int) -> None:
        self.populate("json", faker.json, str.encode, total_messages)

    def populate_json_schema(
        self,
        serializer: JSONSerializer,
        faker: Faker,
        total_messages: int,
    ) -> None:
        self._populate_schema(
            "json-schema",
            JsonUser,
            serializer,
            faker,
            total_messages,
        )

    def populate_protobuf(self, faker: Faker, total_messages: int) -> None:
        self.populate(
            "protobuf",
            partial(fake_user, ProtobufUser, faker),
            serialize_protobuf,
            total_messages,
        )

    def populate_protobuf_schema(
        self,
        serializer: ProtobufSerializer,
        faker: Faker,
        total_messages: int,
    ) -> None:
        self._populate_schema(
            "protobuf-schema",
            ProtobufUser,
            serializer,
            faker,
            total_messages,
        )

    def populate_avro(self, faker: Faker, total_messages: int) -> None:
        self.populate(
            "avro",
            partial(fake_user, AvroUser, faker),
            serialize_avro,
            total_messages,
        )

    def populate_avro_schema(
        self,
        serializer: AvroSerializer,
        faker: Faker,
        total_messages: int,
    ) -> None:
        self._populate_schema("avro-schema", AvroUser, serializer, faker, total_messages)

    def _populate_schema(
        self,
        topic: str,
        model: Callable[..., Any],
        serializer: Callable[[Any, SerializationContext], Any],
        faker: Faker,
        total_messages: int,
    ) -> None:
        self.populate(
            topic,
            partial(fake_user, model, faker),
            partial(serialize_with_context, serializer=serializer, topic=topic),
            total_messages,
        )

    def populate_errors(
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


def validate_topics(
    ctx: click.Context, param: click.Parameter, value: tuple[str, ...]
) -> tuple[str, ...] | None:
    if len(value) != len(set(value)):
        raise click.BadParameter("Each topic may only be selected once.", ctx=ctx, param=param)
    return value or None


@click.command()
@click.option("--messages", default=1000, help="Number of messages to send.")
@click.option(
    "--topic",
    "selected_topics",
    type=click.Choice(AVAILABLE_TOPICS),
    multiple=True,
    callback=validate_topics,
    help="Topic to populate. Repeat for a subset; omit to populate all topics.",
)
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
    selected_topics: tuple[str, ...] | None,
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
        model_to_dict,
    )
    json_serializer = JSONSerializer(
        file_to_str(JSON_USER_SCHEMA),
        registry_client,
        model_to_dict,
    )
    protobuf_serializer = ProtobufSerializer(
        ProtobufUser, registry_client, {"use.deprecated.format": False}
    )
    faker = Faker()
    populator = Populator(
        kafka_config,
        partitions=partitions,
        replication_factor=replication_factor,
        min_insync_replicas=min_insync_replicas,
    )

    def topic_population(
        topic: str,
        action: Callable[..., None],
        *args: Any,
    ) -> tuple[str, Callable[[], None]]:
        return topic, partial(action, *args, messages)

    topics: list[tuple[str, Callable[[], None]]] = [
        topic_population("string", populator.populate_string, faker),
        topic_population("integer", populator.populate_integer, faker),
        topic_population("long", populator.populate_long, faker),
        topic_population("float", populator.populate_float, faker),
        topic_population("double", populator.populate_double, faker),
        topic_population("boolean", populator.populate_boolean, faker),
        topic_population(NULL_TOPIC, populator.populate_null),
        topic_population("json", populator.populate_json, faker),
        topic_population("json-schema", populator.populate_json_schema, json_serializer, faker),
        topic_population("protobuf", populator.populate_protobuf, faker),
        topic_population(
            "protobuf-schema",
            populator.populate_protobuf_schema,
            protobuf_serializer,
            faker,
        ),
        topic_population("avro", populator.populate_avro, faker),
        topic_population(
            "avro-schema",
            populator.populate_avro_schema,
            avro_serializer,
            faker,
        ),
        topic_population(ERRORS_TOPIC, populator.populate_errors, json_serializer, faker),
    ]
    if selected_topics is not None:
        actions_by_topic = dict(topics)
        topics = [(topic, actions_by_topic[topic]) for topic in selected_topics]

    console = Console()
    with console.status("", spinner="dots") as status:
        for topic, action in topics:
            run_population(
                console,
                status,
                populator,
                topic,
                action,
            )


if __name__ == "__main__":
    main()
