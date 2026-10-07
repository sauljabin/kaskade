from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from struct import Struct
from typing import Any

from confluent_kafka.schema_registry.error import SchemaRegistryError
from confluent_kafka.serialization import MessageField, SerializationError
from google.protobuf.message import DecodeError

from kaskade.apicurio import ApicurioRegistryError
from kaskade.configs import (
    APICURIO,
    CONFLUENT,
    SCHEMA_REGISTRY_HEADER_SIZE,
    SCHEMA_REGISTRY_MAGIC_BYTE,
)

# The magic byte followed by the 4-byte schema ID.
REGISTRY_HEADER = Struct(">bI")


class DeserializationError(Exception):
    """Raised when configuration, framing, or payload data cannot be deserialized."""


DESERIALIZATION_EXCEPTIONS: tuple[type[Exception], ...] = (
    DeserializationError,
    EOFError,
    OSError,
    ValueError,
    SchemaRegistryError,
    SerializationError,
    DecodeError,
    ApicurioRegistryError,
)
SCHEMA_METADATA_EXCEPTIONS: tuple[type[Exception], ...] = (
    *DESERIALIZATION_EXCEPTIONS,
    AttributeError,
    TypeError,
)


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


class BytesEncoding(Enum):
    BASE64 = auto()
    HEX = auto()
    BYTE_ARRAY = auto()
    ESCAPED = auto()

    def __str__(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def from_str(cls, value: str) -> "BytesEncoding":
        return cls[value.upper().replace("-", "_")]

    @classmethod
    def from_config(
        cls,
        config: dict[str, str],
        context: MessageField = MessageField.NONE,
    ) -> "BytesEncoding":
        return cls.from_str(_scoped_property(config, "encoding", context, str(cls.BASE64)))


@dataclass(frozen=True)
class RegistrySchema:
    id: int
    subject: str
    version: int
    type: str

    def dict(self) -> dict[str, int | str]:
        return {
            "provider": CONFLUENT,
            "id": self.id,
            "subject": self.subject,
            "version": self.version,
            "type": self.type,
        }


@dataclass(frozen=True)
class ApicurioRegistrySchema:
    id: int
    id_kind: str
    type: str
    group: str | None = None
    artifact: str | None = None
    version: str | None = None

    def dict(self) -> dict[str, int | str]:
        result: dict[str, int | str] = {
            "provider": APICURIO,
            "id": self.id,
            "id_kind": self.id_kind,
            "type": self.type,
        }
        if self.group is not None:
            result["group"] = self.group
        if self.artifact is not None:
            result["artifact"] = self.artifact
        if self.version is not None:
            result["version"] = self.version
        return result


@dataclass(frozen=True)
class DeserializationResult:
    content: Any
    schema: RegistrySchema | ApicurioRegistrySchema | None = None


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

    def close(self) -> None:  # noqa: B027 - optional hook; most deserializers own no resources
        """Release resources held by the deserializer."""


def _require_context(context: MessageField) -> None:
    if context == MessageField.NONE:
        raise DeserializationError("Context is needed: KEY or VALUE")


def _require_field(topic: str | None, context: MessageField) -> str:
    if topic is None:
        raise DeserializationError("Topic name needed")
    _require_context(context)
    return topic


def _registry_header(data: bytes) -> tuple[int, int]:
    """Return the magic byte and schema ID of a framed Registry payload."""
    magic, schema_id = REGISTRY_HEADER.unpack(data[:SCHEMA_REGISTRY_HEADER_SIZE])
    return int(magic), int(schema_id)


def _has_registry_header(data: bytes) -> bool:
    if len(data) <= SCHEMA_REGISTRY_HEADER_SIZE:
        return False
    magic, _ = _registry_header(data)
    return magic == SCHEMA_REGISTRY_MAGIC_BYTE


def _deserialize_avro(deserialize: Callable[..., Any], *args: Any) -> Any:
    try:
        return deserialize(*args)
    except IndexError as ex:
        raise DeserializationError(str(ex)) from ex


def _scoped_property(
    config: dict[str, str],
    property_name: str,
    context: MessageField,
    default: str,
) -> str:
    if context != MessageField.NONE:
        scoped_name = f"{context.name.lower()}.{property_name}"
        if scoped_name in config:
            return config[scoped_name]
    return config.get(property_name, default)
