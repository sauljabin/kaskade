from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from confluent_kafka.serialization import MessageField

from kaskade.deserializers import DESERIALIZATION_EXCEPTIONS, Deserialization, Deserializer

_NOT_DESERIALIZED = object()


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
    _deserialized: Any = field(default=_NOT_DESERIALIZED, init=False, repr=False)

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
            self._deserialized = str(self.value)
            return self._deserialized

        try:
            self._deserialized = self.value_deserializer.deserialize(self.value)
        except DESERIALIZATION_EXCEPTIONS:
            # it doesn't matter to show the binaries
            self._deserialized = str(self.value)
        return self._deserialized

    def value_str(self) -> str:
        return str(self.value_deserialized())


@dataclass(frozen=True)
class DeserializationOutcome:
    requested: Deserialization
    content: Any
    error: Exception | None = None

    @property
    def used_fallback(self) -> bool:
        return self.error is not None

    def dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "deserializer": self.requested.name,
            "content": self.content,
        }
        if self.error is not None:
            result |= {
                "fallback": Deserialization.BYTES.name,
                "error": str(self.error),
            }
        return result


@dataclass(eq=False)
class Record:
    topic: str = ""
    partition: int = -1
    offset: int = -1
    timestamp: str = ""
    key: bytes | None = None
    value: bytes | None = None
    headers: list[Header] = field(default_factory=list)
    key_deserialization: Deserialization = Deserialization.BYTES
    value_deserialization: Deserialization = Deserialization.BYTES
    key_deserializer: Deserializer | None = None
    value_deserializer: Deserializer | None = None
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
            "timestamp": self.timestamp,
            "headers": [(header.key, header.value_deserialized()) for header in self.headers],
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
            )
        assert isinstance(self._value_outcome, DeserializationOutcome)
        return self._value_outcome

    def _deserialize(
        self,
        raw: bytes | None,
        requested: Deserialization,
        deserializer: Deserializer | None,
        field: MessageField,
    ) -> DeserializationOutcome:
        if raw is None:
            return DeserializationOutcome(requested, None)
        if deserializer is None:
            return DeserializationOutcome(requested, str(raw))
        try:
            return DeserializationOutcome(
                requested,
                deserializer.deserialize(raw, self.topic, field),
            )
        except DESERIALIZATION_EXCEPTIONS as ex:
            return DeserializationOutcome(requested, str(raw), ex)

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
        return str(self.key_deserialized())

    def value_str(self) -> str:
        return str(self.value_deserialized())
