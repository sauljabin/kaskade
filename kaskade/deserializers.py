import json
import struct
from abc import abstractmethod, ABC
from enum import Enum, auto
from io import BytesIO
from typing import Any, Callable

import avro.schema
from avro.io import BinaryDecoder, DatumReader
from confluent_kafka.schema_registry import SchemaRegistryClient

from kaskade.configs import SCHEMA_REGISTRY_MAGIC_BYTE


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
    def deserialize(self, data: bytes) -> Any:
        pass


class DefaultDeserializer(Deserializer):
    def deserialize(self, data: bytes) -> Any:
        return str(data)


class StringDeserializer(Deserializer):

    def deserialize(self, data: bytes) -> Any:
        return data.decode("utf-8")


class ProtobufDeserializer(Deserializer):
    def __init__(self, descriptor: str, class_name: str):
        self.descriptor = descriptor
        self.class_name = class_name

    def deserialize(self, data: bytes) -> Any:
        pass


class DeserializerFactory:
    def __init__(
        self,
        schema_registry_config: dict[str, str] | None = None,
        protobuf_config: dict[str, str] | None = None,
    ):
        if schema_registry_config:
            self.schema_registry_client = SchemaRegistryClient(schema_registry_config)

        # if protobuf_config:
        #     self.protobuf_deserializer = ProtobufDeserializer(protobuf_config)

    def make_deserializer(self, deserialization_format: Format) -> Callable[[bytes], Any]:
        def avro_deserializer(raw_bytes: bytes) -> Any:
            if self.schema_registry_client is None:
                raise Exception("Schema Registry is not configured")

            magic, schema_id = struct.unpack(">bI", raw_bytes[:5])

            if magic != SCHEMA_REGISTRY_MAGIC_BYTE:
                raise Exception(
                    "Unexpected magic byte. This message was not produced with a Confluent Schema Registry serializer"
                )

            schema = avro.schema.parse(self.schema_registry_client.get_schema(schema_id).schema_str)
            binary_value = BinaryDecoder(BytesIO(raw_bytes[5:]))
            reader = DatumReader(schema)
            return reader.read(binary_value)

        def default_deserializer(raw_bytes: bytes) -> Any:
            return str(raw_bytes)

        def string_deserializer(raw_bytes: bytes) -> Any:
            return raw_bytes.decode("utf-8")

        def integer_deserializer(raw_bytes: bytes) -> Any:
            return struct.unpack(">i", raw_bytes)[0]

        def json_deserializer(raw_bytes: bytes) -> Any:
            try:
                return json.loads(raw_bytes)
            except UnicodeDecodeError:
                # in case that the json has a confluent schema registry magic byte
                return json.loads(raw_bytes[5:])

        def long_deserializer(raw_bytes: bytes) -> Any:
            return struct.unpack(">q", raw_bytes)[0]

        def double_deserializer(raw_bytes: bytes) -> Any:
            return struct.unpack(">d", raw_bytes)[0]

        def float_deserializer(raw_bytes: bytes) -> Any:
            return struct.unpack(">f", raw_bytes)[0]

        def bool_deserializer(raw_bytes: bytes) -> Any:
            return struct.unpack(">?", raw_bytes)[0]

        match deserialization_format:
            case Format.STRING:
                return string_deserializer
            case Format.JSON:
                return json_deserializer
            case Format.INTEGER:
                return integer_deserializer
            case Format.LONG:
                return long_deserializer
            case Format.DOUBLE:
                return double_deserializer
            case Format.FLOAT:
                return float_deserializer
            case Format.BOOLEAN:
                return bool_deserializer
            case Format.AVRO:
                return avro_deserializer
            case _:
                return default_deserializer
