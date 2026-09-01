import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from struct import error as StructError
from struct import unpack
from typing import Any

from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer as ConfluentAvroDeserializer
from confluent_kafka.schema_registry.error import SchemaRegistryError
from confluent_kafka.schema_registry.json_schema import (
    JSONDeserializer as ConfluentJsonDeserializer,
)
from confluent_kafka.schema_registry.protobuf import (
    ProtobufDeserializer as ConfluentProtobufDeserializer,
)
from confluent_kafka.serialization import MessageField, SerializationContext, SerializationError
from google.protobuf.descriptor_pb2 import FileDescriptorSet
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError, Message
from google.protobuf.message_factory import GetMessages

from kaskade import logger
from kaskade.configs import SCHEMA_REGISTRY_MAGIC_BYTE
from kaskade.utils import avro_to_py, file_to_bytes, unpack_bytes


class DeserializationError(Exception):
    """Raised when configuration, framing, or payload data cannot be deserialized."""


def _unpack_payload(struct_format: str, data: bytes) -> Any:
    try:
        return unpack_bytes(struct_format, data)
    except StructError as ex:
        raise DeserializationError(str(ex)) from ex


def _deserialize_avro(deserialize: Callable[..., Any], *args: Any) -> Any:
    try:
        return deserialize(*args)
    except IndexError as ex:
        raise DeserializationError(str(ex)) from ex


DESERIALIZATION_EXCEPTIONS: tuple[type[Exception], ...] = (
    DeserializationError,
    EOFError,
    OSError,
    ValueError,
    SchemaRegistryError,
    SerializationError,
    DecodeError,
)
SCHEMA_METADATA_EXCEPTIONS = DESERIALIZATION_EXCEPTIONS + (AttributeError, TypeError)


class Deserialization(Enum):
    BYTES = auto()
    BOOLEAN = auto()
    STRING = auto()
    LONG = auto()
    INTEGER = auto()
    DOUBLE = auto()
    FLOAT = auto()
    JSON = auto()
    AVRO = auto()
    PROTOBUF = auto()
    REGISTRY = auto()

    def __str__(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return str(self)

    @classmethod
    def from_str(cls, value: str) -> "Deserialization":
        return Deserialization[value.upper()]

    @classmethod
    def str_list(cls) -> list[str]:
        return [str(name) for name in Deserialization]


@dataclass(frozen=True)
class RegistrySchema:
    id: int
    subject: str
    version: int
    type: str

    def dict(self) -> dict[str, int | str]:
        return {
            "id": self.id,
            "subject": self.subject,
            "version": self.version,
            "type": self.type,
        }


@dataclass(frozen=True)
class DeserializationResult:
    content: Any
    schema: RegistrySchema | None = None


class Deserializer(ABC):
    @abstractmethod
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        pass

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        return DeserializationResult(self.deserialize(data, topic, context))


class DefaultDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return str(data)


class StringDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return data.decode("utf-8")


class BooleanDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">?", data)


class FloatDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">f", data)


class DoubleDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">d", data)


class LongDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">q", data)


class IntegerDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">i", data)


class JsonDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return json.loads(_without_confluent_header(data))


class RegistryDeserializer(Deserializer):
    def __init__(self, registry_config: dict[str, str]):
        self.registry_client = SchemaRegistryClient(registry_config)
        self.avro_deserializer = ConfluentAvroDeserializer(self.registry_client)
        self.json_deserializer = ConfluentJsonDeserializer(
            None, schema_registry_client=self.registry_client
        )
        self._schema_cache: dict[tuple[int, str, MessageField], RegistrySchema | None] = {}

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        _, schema_type = self._schema(data, topic, context)
        return self._deserialize_content(data, topic, context, schema_type)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        schema_id, schema_type = self._schema(data, topic, context)
        content = self._deserialize_content(data, topic, context, schema_type)
        assert topic is not None
        return DeserializationResult(
            content,
            self._resolve_schema(schema_id, schema_type, topic, context),
        )

    def _schema(
        self,
        data: bytes,
        topic: str | None,
        context: MessageField,
    ) -> tuple[int, str]:
        if topic is None:
            raise DeserializationError("Topic name needed")

        if context == MessageField.NONE:
            raise DeserializationError("Context is needed: KEY or VALUE")

        if len(data) <= 5:
            raise DeserializationError(
                f"Expecting data framing of length 6 bytes or more but total data size is {len(data)} bytes. This message was not produced with a Confluent Schema Registry serializer"
            )

        magic, schema_id = unpack(">bI", data[:5])
        if magic != SCHEMA_REGISTRY_MAGIC_BYTE:
            raise DeserializationError(
                f"Unexpected magic byte {magic}. This message was not produced with a Confluent Schema Registry serializer"
            )

        schema = self.registry_client.get_schema(schema_id)
        if schema.schema_type is None:
            raise DeserializationError("Schema type not supported")
        return schema_id, schema.schema_type.upper()

    def _deserialize_content(
        self,
        data: bytes,
        topic: str | None,
        context: MessageField,
        schema_type: str,
    ) -> Any:
        assert topic is not None
        match schema_type:
            case "JSON":
                return self.json_deserializer(data, SerializationContext(topic, context))
            case "AVRO":
                return _deserialize_avro(
                    self.avro_deserializer,
                    data,
                    SerializationContext(topic, context),
                )
            case _:
                raise DeserializationError("Schema type not supported")

    def _resolve_schema(
        self,
        schema_id: int,
        schema_type: str,
        topic: str,
        context: MessageField,
    ) -> RegistrySchema | None:
        cache_key = (schema_id, topic, context)
        if cache_key in self._schema_cache:
            return self._schema_cache[cache_key]

        try:
            registrations = self.registry_client.get_schema_versions(schema_id)
            result = self._select_schema(
                schema_id,
                schema_type,
                topic,
                context,
                registrations,
            )
        except SCHEMA_METADATA_EXCEPTIONS as ex:
            logger.warning(
                "schema metadata lookup failed schema_id=%d topic=%s field=%s error=%s",
                schema_id,
                topic,
                context.name,
                ex,
            )
            result = None

        self._schema_cache[cache_key] = result
        return result

    @staticmethod
    def _select_schema(
        schema_id: int,
        schema_type: str,
        topic: str,
        context: MessageField,
        registrations: list[Any],
    ) -> RegistrySchema | None:
        candidates = [
            registration
            for registration in registrations
            if registration.subject is not None and registration.version is not None
        ]
        selected = candidates[0] if len(candidates) == 1 else None
        if selected is None:
            conventional_subject = f"{topic}-{context.name.lower()}"
            conventional = [
                registration
                for registration in candidates
                if registration.subject == conventional_subject
            ]
            selected = conventional[0] if len(conventional) == 1 else None
        if selected is None:
            return None
        return RegistrySchema(
            id=schema_id,
            subject=selected.subject,
            version=selected.version,
            type=schema_type,
        )


class AvroDeserializer(Deserializer):
    def __init__(self, avro_config: dict[str, str]):
        self.key_path = avro_config.get("key")
        self.value_path = avro_config.get("value")
        self.framing = avro_config.get("framing", "raw")

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        schema_path: str | None = None

        if context == MessageField.NONE:
            raise DeserializationError("Context is needed: KEY or VALUE")

        if context == MessageField.KEY:
            if self.key_path is None:
                raise DeserializationError("Avro schema was not provided for context KEY")
            schema_path = self.key_path

        if context == MessageField.VALUE:
            if self.value_path is None:
                raise DeserializationError("Avro schema was not provided for context VALUE")
            schema_path = self.value_path

        if schema_path is None:
            raise DeserializationError("Avro schema file not found")

        payload = self._payload(data)
        return _deserialize_avro(avro_to_py, schema_path, payload)

    def _payload(self, data: bytes) -> bytes:
        if self.framing == "raw":
            return data
        if self.framing == "confluent" and _has_confluent_header(data):
            return data[5:]
        if self.framing == "confluent":
            raise DeserializationError("Confluent Avro framing header not found")
        raise DeserializationError(f"Unsupported Avro framing: {self.framing}")


class ProtobufDeserializer(Deserializer):
    def __init__(self, protobuf_config: dict[str, str]):
        self.descriptor_path = protobuf_config.get("descriptor")
        self.key_class = protobuf_config.get("key")
        self.value_class = protobuf_config.get("value")
        self.descriptor_classes: dict[str, type[Message]] | None = None

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        if topic is None:
            raise DeserializationError("Topic name needed")
        message_class = self._message_class(context)
        if _has_confluent_header(data):
            return self._deserialize_confluent(data, topic, context, message_class)

        new_message = message_class()
        new_message.ParseFromString(data)
        return MessageToDict(new_message, always_print_fields_with_no_presence=True)

    def _message_class(self, context: MessageField) -> type[Message]:
        class_name = self._class_name(context)
        if self.descriptor_path is None:
            raise DeserializationError("Descriptor not found")
        if self.descriptor_classes is None:
            descriptor = FileDescriptorSet.FromString(file_to_bytes(self.descriptor_path))
            self.descriptor_classes = GetMessages(descriptor.file)
        message_class = self.descriptor_classes.get(class_name)
        if message_class is None:
            raise DeserializationError("Deserialization class not found")
        return message_class

    def _class_name(self, context: MessageField) -> str:
        if context == MessageField.NONE:
            raise DeserializationError("Context is needed: KEY or VALUE")
        class_name = self.key_class if context == MessageField.KEY else self.value_class
        if class_name is None:
            raise DeserializationError(
                f"Protobuf message name not provided for context {context.name}"
            )
        return class_name

    @staticmethod
    def _deserialize_confluent(
        data: bytes,
        topic: str,
        context: MessageField,
        message_class: type[Message],
    ) -> Any:
        deserializer = ConfluentProtobufDeserializer(
            message_class, {"use.deprecated.format": False}
        )
        message = deserializer(data, SerializationContext(topic, context))
        return MessageToDict(message, always_print_fields_with_no_presence=True)


class DeserializerPool:
    def __init__(
        self,
        registry_config: dict[str, str] | None = None,
        protobuf_config: dict[str, str] | None = None,
        avro_config: dict[str, str] | None = None,
    ):
        self.registry_deserializer: RegistryDeserializer | None = None
        self.protobuf_deserializer: ProtobufDeserializer | None = None
        self.avro_deserializer: AvroDeserializer | None = None

        if registry_config:
            self.registry_deserializer = RegistryDeserializer(registry_config)

        if avro_config:
            self.avro_deserializer = AvroDeserializer(avro_config)

        if protobuf_config:
            self.protobuf_deserializer = ProtobufDeserializer(protobuf_config)

        self.string_deserializer = StringDeserializer()
        self.json_deserializer = JsonDeserializer()
        self.integer_deserializer = IntegerDeserializer()
        self.float_deserializer = FloatDeserializer()
        self.double_deserializer = DoubleDeserializer()
        self.boolean_deserializer = BooleanDeserializer()
        self.long_deserializer = LongDeserializer()
        self.default_deserializer = DefaultDeserializer()
        self._deserializers: dict[Deserialization, Deserializer | None] = {
            Deserialization.BYTES: self.default_deserializer,
            Deserialization.STRING: self.string_deserializer,
            Deserialization.JSON: self.json_deserializer,
            Deserialization.INTEGER: self.integer_deserializer,
            Deserialization.LONG: self.long_deserializer,
            Deserialization.DOUBLE: self.double_deserializer,
            Deserialization.FLOAT: self.float_deserializer,
            Deserialization.BOOLEAN: self.boolean_deserializer,
            Deserialization.REGISTRY: self.registry_deserializer,
            Deserialization.AVRO: self.avro_deserializer,
            Deserialization.PROTOBUF: self.protobuf_deserializer,
        }

    def get(self, deserialization_format: Deserialization) -> Deserializer:
        try:
            deserializer = self._deserializers[deserialization_format]
        except KeyError as ex:
            raise DeserializationError(
                f"Deserializer not registered: {deserialization_format}"
            ) from ex
        if deserializer is None:
            configured_name = {
                Deserialization.REGISTRY: "Schema Registry",
                Deserialization.AVRO: "Avro",
                Deserialization.PROTOBUF: "Protobuf",
            }[deserialization_format]
            raise DeserializationError(f"{configured_name} is not configured")
        return deserializer


def _has_confluent_header(data: bytes) -> bool:
    if len(data) <= 5:
        return False
    magic = int(unpack(">bI", data[:5])[0])
    return magic == SCHEMA_REGISTRY_MAGIC_BYTE


def _without_confluent_header(data: bytes) -> bytes:
    return data[5:] if _has_confluent_header(data) else data
