import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

from confluent_kafka.serialization import MessageField

from kaskade.deserializers import (
    DESERIALIZATION_EXCEPTIONS,
    BytesEncoding,
    Deserialization,
    DeserializationResult,
    Deserializer,
    RegistrySchema,
)

_NOT_DESERIALIZED = object()


def bytes_data(data: bytes, bytes_encoding: BytesEncoding) -> str | list[int]:
    match bytes_encoding:
        case BytesEncoding.BASE64:
            return base64.b64encode(data).decode("ascii")
        case BytesEncoding.HEX:
            return data.hex()
        case BytesEncoding.BYTE_ARRAY:
            return list(data)
        case BytesEncoding.PYTHON:
            return str(data)


def content_str(content: Any, bytes_encoding: BytesEncoding) -> str:
    if isinstance(content, bytes):
        return str(bytes_data(content, bytes_encoding))
    if isinstance(content, bool):
        return str(content).lower()
    return str(content)


def json_content(content: Any, bytes_encoding: BytesEncoding) -> Any:
    if isinstance(content, bytes):
        return bytes_data(content, bytes_encoding)
    return content


def bytes_deserializer(bytes_encoding: BytesEncoding) -> dict[str, str]:
    return {
        "type": Deserialization.BYTES.name,
        "encoding": bytes_encoding.name,
    }


@dataclass(eq=False)
class Node:
    id: int = -1
    host: str = ""
    port: int = -1
    rack: str | None = ""

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.host}:{self.port}/{self.id}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Node):
            return self.id == other.id
        return False


@dataclass(eq=False)
class GroupMember:
    id: str = ""
    client_id: str = ""
    group: str = ""
    host: str = ""
    instance_id: str | None = ""
    assignment: list[int] = field(default_factory=list)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self.id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GroupMember):
            return (self.group, self.id) == (other.group, other.id)
        return False


@dataclass(eq=False)
class GroupPartition:
    id: int = -1
    topic: str = ""
    group: str = ""
    offset: int = 0
    low: int = 0
    high: int = 0

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self.id)

    def lag_count(self) -> int:
        if self.high <= 0:
            return 0
        elif self.offset < 0:
            return max(0, self.high - self.low)
        else:
            return max(0, self.high - self.offset)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GroupPartition):
            return (self.group, self.topic, self.id) == (other.group, other.topic, other.id)
        return False


@dataclass(eq=False)
class Group:
    id: str = ""
    coordinator: Node | None = None
    state: str = ""
    partition_assignor: str = ""
    members: list[GroupMember] = field(default_factory=list)
    partitions: list[GroupPartition] = field(default_factory=list)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.id

    def lag_count(self) -> int:
        return sum(partition.lag_count() for partition in self.partitions)

    def members_count(self) -> int:
        return len(self.members)

    def partitions_count(self) -> int:
        return len(self.partitions)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Group):
            return self.id == other.id
        return False


@dataclass(eq=False)
class Partition:
    id: int = -1
    leader: int = -1
    replicas: list[int] = field(default_factory=list)
    isrs: list[int] = field(default_factory=list)
    low: int = 0
    high: int = 0
    topic: str = ""

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self.id)

    def records_count(self) -> int:
        return max(0, self.high - self.low)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Partition):
            return (self.topic, self.id) == (other.topic, other.id)
        return False


@dataclass(eq=False)
class Topic:
    name: str = ""
    partitions: list[Partition] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    records_state: "MetricState" = field(default_factory=lambda: MetricState.LOADING)
    groups_state: "MetricState" = field(default_factory=lambda: MetricState.LOADING)

    def partitions_count(self) -> int:
        return len(self.partitions)

    def groups_count(self) -> int:
        return len(self.groups)

    def group_members_count(self) -> int:
        return sum(group.members_count() for group in self.groups)

    def replicas_count(self) -> int:
        return max((len(partition.replicas) for partition in self.partitions), default=0)

    def isrs_count(self) -> int:
        return min((len(partition.isrs) for partition in self.partitions), default=0)

    def lag(self) -> int:
        return sum(group.lag_count() for group in self.groups)

    def records_count(self) -> int:
        return sum(partition.records_count() for partition in self.partitions)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Topic):
            return self.name == other.name
        return False


@dataclass(frozen=True)
class TopicConfiguration:
    name: str
    value: str


class CleanupPolicy(Enum):
    DELETE = auto()
    COMPACT = auto()

    def __str__(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return str(self)

    @classmethod
    def from_str(cls, value: str) -> "CleanupPolicy":
        return CleanupPolicy[value.upper()]

    @classmethod
    def str_list(cls) -> list[str]:
        return [str(policy) for policy in CleanupPolicy]


class MetricState(Enum):
    LOADING = auto()
    READY = auto()
    UNAVAILABLE = auto()


class PartitionOffset(Enum):
    EARLIEST = auto()


@dataclass(frozen=True)
class PartitionSelection:
    partition: int
    offset: int | PartitionOffset | None = None


@dataclass(eq=False)
class Header:
    key: str = ""
    value: bytes | None = None
    value_deserializer: Deserializer | None = None
    fallback_bytes_encoding: BytesEncoding = BytesEncoding.BASE64
    _deserialized: Any = field(default=_NOT_DESERIALIZED, init=False, repr=False)
    _error: Exception | None = field(default=None, init=False, repr=False)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.key}:{self.value_str()}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Header):
            return (self.key, self.value) == (other.key, other.value)
        return False

    def value_deserialized(self) -> Any:
        if self._deserialized is not _NOT_DESERIALIZED:
            return self._deserialized

        if self.value is None:
            self._deserialized = None
            return self._deserialized

        if self.value_deserializer is None:
            self._deserialized = self.value
            return self._deserialized

        try:
            self._deserialized = self.value_deserializer.deserialize(self.value)
        except DESERIALIZATION_EXCEPTIONS as ex:
            self._deserialized = self.value
            self._error = ex
        return self._deserialized

    def value_str(self) -> str:
        return content_str(self.value_deserialized(), self.fallback_bytes_encoding)

    def dict(self) -> dict[str, Any]:
        value = self.value_deserialized()
        result: dict[str, Any] = {
            "key": self.key,
            "value": json_content(value, self.fallback_bytes_encoding),
        }
        if self._error is not None:
            result["error"] = {
                "message": str(self._error),
                "fallback": bytes_deserializer(self.fallback_bytes_encoding),
            }
        return result


@dataclass(frozen=True)
class DeserializationOutcome:
    requested: Deserialization
    content: Any
    schema: RegistrySchema | None = None
    error: Exception | None = None
    bytes_encoding: BytesEncoding = BytesEncoding.BASE64

    @property
    def used_fallback(self) -> bool:
        return self.error is not None

    def dict(self) -> dict[str, Any]:
        deserializer: dict[str, Any] = {"type": self.requested.name}
        if self.schema is not None:
            deserializer["schema"] = self.schema.dict()
        if (
            self.error is None
            and self.requested == Deserialization.BYTES
            and isinstance(self.content, bytes)
        ):
            deserializer["encoding"] = self.bytes_encoding.name
        result = {
            "content": json_content(self.content, self.bytes_encoding),
            "deserializer": deserializer,
        }
        if self.error is not None:
            result["error"] = {
                "message": str(self.error),
                "fallback": bytes_deserializer(self.bytes_encoding),
            }
        return result

    def content_str(self) -> str:
        return content_str(self.content, self.bytes_encoding)


@dataclass(eq=False)
class Record:
    topic: str = ""
    partition: int = -1
    offset: int = -1
    timestamp: datetime | None = None
    key: bytes | None = None
    value: bytes | None = None
    headers: list[Header] = field(default_factory=list)
    key_deserialization: Deserialization = Deserialization.BYTES
    value_deserialization: Deserialization = Deserialization.BYTES
    key_deserializer: Deserializer | None = None
    value_deserializer: Deserializer | None = None
    key_bytes_encoding: BytesEncoding = BytesEncoding.BASE64
    value_bytes_encoding: BytesEncoding = BytesEncoding.BASE64
    fallback_bytes_encoding: BytesEncoding = BytesEncoding.BASE64
    _key_outcome: DeserializationOutcome | object = field(
        default=_NOT_DESERIALIZED, init=False, repr=False
    )
    _value_outcome: DeserializationOutcome | object = field(
        default=_NOT_DESERIALIZED, init=False, repr=False
    )

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.partition}/{self.offset}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Record):
            return (self.topic, self.partition, self.offset) == (
                other.topic,
                other.partition,
                other.offset,
            )
        return False

    def headers_count(self) -> int:
        return len(self.headers)

    def dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "timestamp": self.timestamp_json(),
            "headers": [header.dict() for header in self.headers],
            "key": self.key_outcome().dict(),
            "value": self.value_outcome().dict(),
        }

    def key_outcome(self) -> DeserializationOutcome:
        if self._key_outcome is _NOT_DESERIALIZED:
            self._key_outcome = self._deserialize(
                self.key,
                self.key_deserialization,
                self.key_deserializer,
                MessageField.KEY,
                self.key_bytes_encoding,
                self.fallback_bytes_encoding,
            )
        assert isinstance(self._key_outcome, DeserializationOutcome)
        return self._key_outcome

    def value_outcome(self) -> DeserializationOutcome:
        if self._value_outcome is _NOT_DESERIALIZED:
            self._value_outcome = self._deserialize(
                self.value,
                self.value_deserialization,
                self.value_deserializer,
                MessageField.VALUE,
                self.value_bytes_encoding,
                self.fallback_bytes_encoding,
            )
        assert isinstance(self._value_outcome, DeserializationOutcome)
        return self._value_outcome

    def _deserialize(
        self,
        raw: bytes | None,
        requested: Deserialization,
        deserializer: Deserializer | None,
        field: MessageField,
        bytes_encoding: BytesEncoding,
        fallback_bytes_encoding: BytesEncoding,
    ) -> DeserializationOutcome:
        if raw is None:
            return DeserializationOutcome(requested, None, bytes_encoding=bytes_encoding)
        if deserializer is None:
            return DeserializationOutcome(requested, raw, bytes_encoding=bytes_encoding)
        try:
            result = self._deserialize_result(deserializer, raw, field)
            return DeserializationOutcome(
                requested,
                result.content,
                result.schema,
                bytes_encoding=bytes_encoding,
            )
        except DESERIALIZATION_EXCEPTIONS as ex:
            return DeserializationOutcome(
                requested,
                raw,
                error=ex,
                bytes_encoding=fallback_bytes_encoding,
            )

    def _deserialize_result(
        self,
        deserializer: Deserializer,
        raw: bytes,
        field: MessageField,
    ) -> DeserializationResult:
        if isinstance(deserializer, Deserializer):
            return deserializer.deserialize_with_metadata(raw, self.topic, field)
        return DeserializationResult(deserializer.deserialize(raw, self.topic, field))

    def resolve_deserializations(self) -> None:
        self.key_outcome()
        self.value_outcome()

    def has_deserialization_errors(self) -> bool:
        return self.key_outcome().used_fallback or self.value_outcome().used_fallback

    def key_deserialized(self) -> Any:
        return self.key_outcome().content

    def value_deserialized(self) -> Any:
        return self.value_outcome().content

    def key_str(self) -> str:
        return self.key_outcome().content_str()

    def value_str(self) -> str:
        return self.value_outcome().content_str()

    def timestamp_json(self) -> str | None:
        timestamp = self._timestamp_utc()
        if timestamp is None:
            return None
        return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def timestamp_str(self) -> str:
        timestamp = self._timestamp_utc()
        if timestamp is None:
            return ""
        return timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _timestamp_utc(self) -> datetime | None:
        timestamp = self.timestamp
        if timestamp is None:
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)
