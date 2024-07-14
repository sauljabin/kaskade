import json
from abc import abstractmethod, ABC
from enum import Enum, auto
from typing import Any, Type

from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer as ConfluentAvroDeserializer
from confluent_kafka.schema_registry.protobuf import (
    ProtobufDeserializer as ConfluentProtobufDeserializer,
)
from confluent_kafka.serialization import MessageField
from google.protobuf.descriptor_pb2 import FileDescriptorSet
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessages

from kaskade.utils import unpack_bytes, file_to_bytes


class Format(Enum):
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

    def __str__(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return str(self)

    @classmethod
    def from_str(cls, value: str) -> "Format":
        return Format[value.upper()]

    @classmethod
    def str_list(cls) -> list[str]:
        return [str(key_format) for key_format in Format]


class Deserializer(ABC):
    @abstractmethod
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        pass


class DefaultDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return str(data)


class StringDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return data.decode("utf-8")


class BooleanDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return unpack_bytes(">?", data)


class FloatDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return unpack_bytes(">f", data)


class DoubleDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return unpack_bytes(">d", data)


class LongDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return unpack_bytes(">q", data)


class IntegerDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return unpack_bytes(">i", data)


class JsonDeserializer(Deserializer):
    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        try:
            return json.loads(data)
        except Exception:
            # in case that the json has a confluent schema registry magic byte
            # https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#wire-format
            return json.loads(data[5:])


class AvroDeserializer(Deserializer):
    def __init__(self, schema_registry_config: dict[str, str]):
        registry_client = SchemaRegistryClient(schema_registry_config)
        self.confluent_deserializer = ConfluentAvroDeserializer(registry_client)

    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        return self.confluent_deserializer(data, None)


class ProtobufDeserializer(Deserializer):
    def __init__(self, protobuf_config: dict[str, str]):
        self.descriptor_path = protobuf_config.get("descriptor")
        self.key_class = protobuf_config.get("key")
        self.value_class = protobuf_config.get("value")
        self.descriptor_classes: dict[str, Type[Message]] | None = None

    def deserialize(self, data: bytes, context: MessageField = MessageField.NONE) -> Any:
        if context == MessageField.NONE:
            raise Exception("Context is needed: KEY or VALUE")

        if self.descriptor_path is None:
            raise Exception("Descriptor not found")

        if self.descriptor_classes is None:
            descriptor = FileDescriptorSet.FromString(file_to_bytes(self.descriptor_path))
            self.descriptor_classes = GetMessages(descriptor.file)

        deserialization_class: Type[Message] | None = None

        if context == MessageField.KEY:
            if self.key_class is None:
                raise Exception("Protobuf message name not provided for context KEY")
            deserialization_class = self.descriptor_classes.get(self.key_class)

        if context == MessageField.VALUE:
            if self.value_class is None:
                raise Exception("Protobuf message name not provided for context VALUE")
            deserialization_class = self.descriptor_classes.get(self.value_class)

        if deserialization_class is None:
            raise Exception("Deserialization class not found")

        try:
            new_message = deserialization_class()
            new_message.ParseFromString(data)
            return MessageToDict(new_message, always_print_fields_with_no_presence=True)
        except Exception:
            # in case that the protobuf has a confluent schema registry magic byte
            # https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#wire-format
            protobuf_deserializer = ConfluentProtobufDeserializer(
                deserialization_class, {"use.deprecated.format": False}
            )
            new_message = protobuf_deserializer(data, None)
            return MessageToDict(new_message, always_print_fields_with_no_presence=True)


class DeserializerPool:
    def __init__(
        self,
        schema_registry_config: dict[str, str] | None = None,
        protobuf_config: dict[str, str] | None = None,
    ):
        if schema_registry_config:
            self.avro_deserializer = AvroDeserializer(schema_registry_config)

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

    def get(self, deserialization_format: Format) -> Deserializer:
        match deserialization_format:
            case Format.STRING:
                return self.string_deserializer
            case Format.JSON:
                return self.json_deserializer
            case Format.INTEGER:
                return self.integer_deserializer
            case Format.LONG:
                return self.long_deserializer
            case Format.DOUBLE:
                return self.double_deserializer
            case Format.FLOAT:
                return self.float_deserializer
            case Format.BOOLEAN:
                return self.boolean_deserializer
            case Format.AVRO:
                if self.avro_deserializer is None:
                    raise Exception("Schema Registry is not configured")
                return self.avro_deserializer
            case Format.PROTOBUF:
                if self.protobuf_deserializer is None:
                    raise Exception("Protobuf is not configured")
                return self.protobuf_deserializer
            case _:
                return self.default_deserializer
