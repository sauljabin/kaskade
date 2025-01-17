import json
from abc import abstractmethod, ABC
from enum import Enum, auto
from io import BytesIO
from struct import unpack
from typing import Any, Type

from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer as ConfluentAvroDeserializer
from confluent_kafka.schema_registry.json_schema import (
    JSONDeserializer as ConfluentJsonDeserializer,
)
from confluent_kafka.schema_registry.protobuf import (
    ProtobufDeserializer as ConfluentProtobufDeserializer,
)
from confluent_kafka.serialization import MessageField, SerializationContext
from fastavro import schemaless_reader
from fastavro.schema import load_schema
from google.protobuf.descriptor_pb2 import FileDescriptorSet
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessages

from kaskade.configs import SCHEMA_REGISTRY_MAGIC_BYTE
from kaskade.utils import unpack_bytes, file_to_bytes


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


class Deserializer(ABC):
    @abstractmethod
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        pass


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
        return unpack_bytes(">?", data)


class FloatDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return unpack_bytes(">f", data)


class DoubleDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return unpack_bytes(">d", data)


class LongDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return unpack_bytes(">q", data)


class IntegerDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return unpack_bytes(">i", data)


class JsonDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        if len(data) > 5:
            magic, schema_id = unpack(">bI", data[:5])
            if magic == SCHEMA_REGISTRY_MAGIC_BYTE:
                # in case that the json has a confluent schema registry magic byte
                # https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#wire-format
                return json.loads(data[5:])

        return json.loads(data)


class RegistryDeserializer(Deserializer):
    def __init__(self, registry_config: dict[str, str]):
        self.registry_client = SchemaRegistryClient(registry_config)
        self.avro_deserializer = ConfluentAvroDeserializer(self.registry_client)
        self.json_deserializer = ConfluentJsonDeserializer(
            None, schema_registry_client=self.registry_client
        )

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        if topic is None:
            raise Exception("Topic name needed")

        if context == MessageField.NONE:
            raise Exception("Context is needed: KEY or VALUE")

        if len(data) <= 5:
            raise Exception(
                f"Expecting data framing of length 6 bytes or more but total data size is {len(data)} bytes. This message was not produced with a Confluent Schema Registry serializer"
            )

        magic, schema_id = unpack(">bI", data[:5])
        if magic != SCHEMA_REGISTRY_MAGIC_BYTE:
            raise Exception(
                f"Unexpected magic byte {magic}. This message was not produced with a Confluent Schema Registry serializer"
            )

        schema = self.registry_client.get_schema(schema_id)

        match schema.schema_type:
            case "JSON":
                return self.json_deserializer(data, SerializationContext(topic, context))
            case "AVRO":
                return self.avro_deserializer(data, SerializationContext(topic, context))
            case _:
                raise Exception("Schema type not supported")


class AvroDeserializer(Deserializer):
    def __init__(self, avro_config: dict[str, str]):
        self.key_path = avro_config.get("key")
        self.value_path = avro_config.get("value")
        self.descriptor_classes: dict[str, Type[Message]] | None = None

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        schema_path: str | None = None

        if context == MessageField.NONE:
            raise Exception("Context is needed: KEY or VALUE")

        if context == MessageField.KEY:
            if self.key_path is None:
                raise Exception("Avro schema was not provided for context KEY")
            schema_path = self.key_path

        if context == MessageField.VALUE:
            if self.value_path is None:
                raise Exception("Avro schema was not provided for context VALUE")
            schema_path = self.value_path

        if schema_path is None:
            raise Exception("Avro schema file not found")

        if len(data) > 5:
            magic, schema_id = unpack(">bI", data[:5])
            if magic == SCHEMA_REGISTRY_MAGIC_BYTE:
                # in case that the avro has a confluent schema registry magic byte
                # https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#wire-format
                return schemaless_reader(BytesIO(data[5:]), load_schema(schema_path), None)

        return schemaless_reader(BytesIO(data), load_schema(schema_path), None)


class ProtobufDeserializer(Deserializer):
    def __init__(self, protobuf_config: dict[str, str]):
        self.descriptor_path = protobuf_config.get("descriptor")
        self.key_class = protobuf_config.get("key")
        self.value_class = protobuf_config.get("value")
        self.descriptor_classes: dict[str, Type[Message]] | None = None

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        if topic is None:
            raise Exception("Topic name needed")

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

        if len(data) > 5:
            magic, schema_id = unpack(">bI", data[:5])
            if magic == SCHEMA_REGISTRY_MAGIC_BYTE:
                # in case that the protobuf has a confluent schema registry magic byte
                # https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#wire-format
                deserializer_config = {"use.deprecated.format": False}
                protobuf_deserializer = ConfluentProtobufDeserializer(
                    deserialization_class, deserializer_config
                )
                new_message = protobuf_deserializer(data, SerializationContext(topic, context))
                return MessageToDict(new_message, always_print_fields_with_no_presence=True)

        new_message = deserialization_class()
        new_message.ParseFromString(data)
        return MessageToDict(new_message, always_print_fields_with_no_presence=True)


class DeserializerPool:
    def __init__(
        self,
        registry_config: dict[str, str] | None = None,
        protobuf_config: dict[str, str] | None = None,
        avro_config: dict[str, str] | None = None,
    ):
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

    def get(self, deserialization_format: Deserialization) -> Deserializer:
        match deserialization_format:
            case Deserialization.STRING:
                return self.string_deserializer
            case Deserialization.JSON:
                return self.json_deserializer
            case Deserialization.INTEGER:
                return self.integer_deserializer
            case Deserialization.LONG:
                return self.long_deserializer
            case Deserialization.DOUBLE:
                return self.double_deserializer
            case Deserialization.FLOAT:
                return self.float_deserializer
            case Deserialization.BOOLEAN:
                return self.boolean_deserializer
            case Deserialization.REGISTRY:
                if self.registry_deserializer is None:
                    raise Exception("Schema Registry is not configured")
                return self.registry_deserializer
            case Deserialization.AVRO:
                if self.avro_deserializer is None:
                    raise Exception("Avro is not configured")
                return self.avro_deserializer
            case Deserialization.PROTOBUF:
                if self.protobuf_deserializer is None:
                    raise Exception("Protobuf is not configured")
                return self.protobuf_deserializer
            case _:
                return self.default_deserializer
