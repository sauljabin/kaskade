import json
import os
import struct
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from time import sleep
from typing import Any

import click
import httpx
from confluent_kafka import KafkaError, KafkaException, Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka.schema_registry.protobuf import ProtobufSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from faker import Faker
from fastavro import schemaless_writer
from google.protobuf.descriptor_pb2 import FieldDescriptorProto, FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass
from rich.console import Console
from rich.status import Status

from kaskade.authentication import configure_aws_msk_iam
from kaskade.cli_utils import tuple_properties_to_dict, validate_aws_config
from kaskade.configs import AWS_CONFIGS, BOOTSTRAP_SERVERS, MIN_INSYNC_REPLICAS_CONFIG
from kaskade.utils import pack_bytes

AVRO_USER_SCHEMA: dict[str, Any] = {
    "name": "User",
    "type": "record",
    "fields": [{"name": "name", "type": "string"}],
}
JSON_USER_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "User",
    "type": "object",
    "properties": {"name": {"type": "string"}},
}
PROTOBUF_USER_SCHEMA = 'syntax = "proto3"; message User { string name = 1; }'
ERRORS_TOPIC = "errors"
NULL_TOPIC = "null"
APICURIO_JSON_TOPIC = "json-schema-apicurio"
APICURIO_PROTOBUF_TOPIC = "protobuf-schema-apicurio"
APICURIO_AVRO_TOPIC = "avro-schema-apicurio"
LARGE_RECORDS_TOPIC = (
    "consumer-layout-with-an-intentionally-long-topic-name-for-large-record-testing"
)
LARGE_JSON_FIELD = (
    "this_is_an_intentionally_long_json_property_name_for_testing_wrapping_"
    "scrolling_and_large_record_proportions"
)
LARGE_HEADER_KEY = (
    "x-kaskade-intentionally-long-header-key-for-testing-wrapping-scrolling-"
    "and-large-record-proportions"
)
LARGE_HEADER_VALUE = ("intentionally-long-header-value-for-consumer-layout-testing-" * 24).encode()
AVAILABLE_TOPICS = (
    "string",
    "integer",
    "long",
    "float",
    "double",
    "boolean",
    NULL_TOPIC,
    "json",
    LARGE_RECORDS_TOPIC,
    "json-schema",
    "protobuf",
    "protobuf-schema",
    "avro",
    "avro-schema",
    APICURIO_JSON_TOPIC,
    APICURIO_PROTOBUF_TOPIC,
    APICURIO_AVRO_TOPIC,
    ERRORS_TOPIC,
)
ERROR_CASES = ("key", "value", "both", "header", "valid")
MALFORMED_KEY_CASES = frozenset({"key", "both"})
MALFORMED_VALUE_CASES = frozenset({"value", "both"})
MALFORMED_PAYLOAD_BYTES = 32
INVALID_UTF8_HEADER = ("sandbox-invalid-utf8", b"\xff")
NULL_HEADER = ("sandbox-null", None)
FAKE_NUMBER_MIN = 500
FAKE_NUMBER_MAX = 10000


@dataclass
class User:
    name: str

    def __str__(self) -> str:
        return str(vars(self))


def apicurio_frame(artifact_id: int, payload: bytes) -> bytes:
    return struct.pack(">bI", 0, artifact_id) + payload


def protobuf_user_class() -> type[Message]:
    descriptor = FileDescriptorProto(name="user.proto", syntax="proto3")
    user = descriptor.message_type.add(name="User")
    user.field.add(
        name="name",
        number=1,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
        type=FieldDescriptorProto.TYPE_STRING,
    )
    pool = DescriptorPool()
    pool.Add(descriptor)
    return GetMessageClass(pool.FindMessageTypeByName("User"))


ProtobufUser = protobuf_user_class()


def model_to_dict(value: User, _: SerializationContext) -> dict[str, Any]:
    return vars(value)


def fake_user(model: Callable[..., Any], faker: Faker) -> Any:
    return model(name=faker.name())


def serialize_with_context(
    value: Any,
    serializer: Callable[[Any, SerializationContext], Any],
    topic: str,
) -> Any:
    return serializer(value, SerializationContext(topic, MessageField.VALUE))


def serialize_protobuf(value: Message) -> bytes:
    return value.SerializeToString()


def serialize_avro(value: User) -> bytes:
    buffer = BytesIO()
    schemaless_writer(buffer, AVRO_USER_SCHEMA, vars(value))
    return buffer.getvalue()


def apicurio_type_ref(name: str) -> bytes:
    encoded = name.encode()
    message = b"\x0a" + bytes([len(encoded)]) + encoded
    return bytes([len(message)]) + message


class Populator:
    def __init__(
        self,
        kafka_config: dict[str, Any],
        partitions: int = 10,
        replication_factor: int | None = None,
        min_insync_replicas: int | None = None,
        apicurio_registry: str = "http://localhost:18082/apis/registry/v3",
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
        self.apicurio_registry = apicurio_registry.rstrip("/")

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
            self.producer.produce(
                NULL_TOPIC,
                key=None,
                value=None,
                headers=[NULL_HEADER],
            )
        self.producer.flush(5)

    def populate_json(self, faker: Faker, total_messages: int) -> None:
        self.populate("json", faker.json, str.encode, total_messages)

    def populate_large_records(self, total_messages: int) -> None:
        for index in range(total_messages):
            key = {
                LARGE_JSON_FIELD: f"record-key-{index}-" + "intentionally-long-key-content-" * 32
            }
            value = {
                LARGE_JSON_FIELD: (
                    f"record-value-{index}-" + "intentionally-long-value-content-" * 128
                ),
                "nested": {
                    "description": "nested-large-record-content-" * 48,
                    "sequence": index,
                },
            }
            self.producer.produce(
                LARGE_RECORDS_TOPIC,
                key=json.dumps(key).encode(),
                value=json.dumps(value).encode(),
                headers=[(LARGE_HEADER_KEY, LARGE_HEADER_VALUE)],
            )
        self.producer.flush(5)

    def populate_json_schema(
        self,
        serializer: JSONSerializer,
        faker: Faker,
        total_messages: int,
    ) -> None:
        self._populate_schema(
            "json-schema",
            User,
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
            partial(fake_user, User, faker),
            serialize_avro,
            total_messages,
        )

    def populate_avro_schema(
        self,
        serializer: AvroSerializer,
        faker: Faker,
        total_messages: int,
    ) -> None:
        self._populate_schema("avro-schema", User, serializer, faker, total_messages)

    def populate_apicurio_json(self, faker: Faker, total_messages: int) -> None:
        schema_id = self._register_apicurio_schema(
            APICURIO_JSON_TOPIC, "JSON", json.dumps(JSON_USER_SCHEMA), "application/json"
        )
        self.populate(
            APICURIO_JSON_TOPIC,
            partial(fake_user, User, faker),
            lambda value: apicurio_frame(schema_id, json.dumps(vars(value)).encode()),
            total_messages,
        )

    def populate_apicurio_protobuf(self, faker: Faker, total_messages: int) -> None:
        schema_id = self._register_apicurio_schema(
            APICURIO_PROTOBUF_TOPIC, "PROTOBUF", PROTOBUF_USER_SCHEMA, "text/plain"
        )
        self.populate(
            APICURIO_PROTOBUF_TOPIC,
            partial(fake_user, ProtobufUser, faker),
            lambda value: (
                apicurio_frame(schema_id, apicurio_type_ref("User") + value.SerializeToString())
            ),
            total_messages,
        )

    def populate_apicurio_avro(self, faker: Faker, total_messages: int) -> None:
        schema_id = self._register_apicurio_schema(
            APICURIO_AVRO_TOPIC, "AVRO", json.dumps(AVRO_USER_SCHEMA), "application/json"
        )
        self.populate(
            APICURIO_AVRO_TOPIC,
            partial(fake_user, User, faker),
            lambda value: apicurio_frame(schema_id, serialize_avro(value)),
            total_messages,
        )

    def _register_apicurio_schema(
        self, topic: str, artifact_type: str, content: str, content_type: str
    ) -> int:
        response = httpx.post(
            f"{self.apicurio_registry}/groups/default/artifacts",
            json={
                "artifactId": f"{topic}-value",
                "artifactType": artifact_type,
                "firstVersion": {"content": {"content": content, "contentType": content_type}},
            },
        )
        if response.status_code == 409:
            response = httpx.get(
                f"{self.apicurio_registry}/search/versions",
                params={"groupId": "default", "artifactId": f"{topic}-value", "limit": 100},
            )
            response.raise_for_status()
            body = response.json()
            versions = body.get("artifacts", body.get("versions", []))
            if not versions:
                raise ValueError(f"Apicurio artifact exists without a version: {topic}-value")
            return int(versions[-1]["contentId"])
        response.raise_for_status()
        body = response.json()
        return int(body.get("version", body)["contentId"])

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
                User(name=faker.name()),
                SerializationContext(ERRORS_TOPIC, MessageField.KEY),
            )
            value = serializer(
                User(name=faker.name()),
                SerializationContext(ERRORS_TOPIC, MessageField.VALUE),
            )
            if error_case in MALFORMED_KEY_CASES:
                key = self._malformed_payload()
            if error_case in MALFORMED_VALUE_CASES:
                value = self._malformed_payload()
            headers: list[tuple[str, str | bytes | None]] = [
                ("sandbox-error-case", error_case.encode("utf-8"))
            ]
            if error_case == "header":
                headers.append(INVALID_UTF8_HEADER)
            self.producer.produce(
                ERRORS_TOPIC,
                key=key,
                value=value,
                headers=headers,
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
    "--apicurio-registry",
    default="http://localhost:18082/apis/registry/v3",
    help="Native Apicurio Core Registry API v3 URL.",
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
    apicurio_registry: str,
    aws_config: dict[str, str],
) -> None:
    kafka_config = sandbox_kafka_config(bootstrap_servers, aws_config)
    registry_client = SchemaRegistryClient({"url": registry})
    avro_serializer = AvroSerializer(
        registry_client,
        json.dumps(AVRO_USER_SCHEMA),
        model_to_dict,
    )
    json_serializer = JSONSerializer(
        json.dumps(JSON_USER_SCHEMA),
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
        apicurio_registry=apicurio_registry,
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
        topic_population(LARGE_RECORDS_TOPIC, populator.populate_large_records),
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
        topic_population(APICURIO_JSON_TOPIC, populator.populate_apicurio_json, faker),
        topic_population(APICURIO_PROTOBUF_TOPIC, populator.populate_apicurio_protobuf, faker),
        topic_population(APICURIO_AVRO_TOPIC, populator.populate_apicurio_avro, faker),
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
