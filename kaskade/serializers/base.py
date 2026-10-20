import json
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class SerializationError(ValueError):
    """Raised when composer text is not valid for the field's serializer.

    Messages describe the problem without repeating the content.
    """


class Serialization(Enum):
    STRING = auto()
    BYTES = auto()
    BOOLEAN = auto()
    INTEGER = auto()
    LONG = auto()
    FLOAT = auto()
    DOUBLE = auto()
    JSON = auto()
    AVRO = auto()
    PROTOBUF = auto()
    REGISTRY = auto()

    def __str__(self) -> str:
        return self.name.lower()

    @classmethod
    def str_list(cls) -> list[str]:
        return [str(serialization) for serialization in cls]

    @classmethod
    def from_str(cls, value: str) -> "Serialization":
        return cls[value.upper()]


@dataclass(frozen=True)
class SchemaSummary:
    """The registered schema a Registry serializer encodes with, for the Summary."""

    name: str
    version: str
    id: int
    type: str


class Serializer:
    """Turns the composer text of one field into Kafka bytes."""

    label = ""
    """The serializer name the Summary shows."""
    edits_json = False
    """Whether the composer input is JSON, which the editor highlights."""

    def serialize(self, text: str) -> bytes:
        raise NotImplementedError

    def draft_text(self, content: Any) -> str:
        """Return editor text for content loaded from a source document."""
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    @property
    def needs_schema(self) -> bool:
        """Whether resolve() must look up a Registry schema before serialize() works."""
        return False

    @property
    def schema(self) -> SchemaSummary | None:
        return None

    def resolve(self) -> None:
        """Look up the schema; it blocks, so callers run it off the event loop."""


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as ex:
        reason = ex.msg[:1].lower() + ex.msg[1:]
        raise SerializationError(
            f"Invalid JSON, {reason} at line {ex.lineno}, column {ex.colno}"
        ) from ex


def compact_json(content: Any) -> bytes:
    return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class JsonDocumentSerializer(Serializer):
    """Serializers whose content is a JSON document: shown indented and highlighted."""

    edits_json = True

    def draft_text(self, content: Any) -> str:
        return json.dumps(content, ensure_ascii=False, indent=2)
