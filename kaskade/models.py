from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from confluent_kafka.serialization import MessageField

from kaskade import logger
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


@dataclass(eq=False)
class Record:
    topic: str = ""
    partition: int = -1
    offset: int = -1
    date: str = ""
    key: bytes | None = None
    value: bytes | None = None
    headers: list[Header] = field(default_factory=list)
    key_deserialization: Deserialization = Deserialization.BYTES
    value_deserialization: Deserialization = Deserialization.BYTES
    key_deserializer: Deserializer | None = None
    value_deserializer: Deserializer | None = None
    _key_deserialized: Any = field(default=_NOT_DESERIALIZED, init=False, repr=False)
    _value_deserialized: Any = field(default=_NOT_DESERIALIZED, init=False, repr=False)
    _key_error: str | None = field(default=None, init=False, repr=False)
    _value_error: str | None = field(default=None, init=False, repr=False)

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

    @staticmethod
    def _field_dict(requested: Deserialization, content: Any, error: str | None) -> dict[str, Any]:
        field_dict: dict[str, Any] = {"deserializer": requested.name, "content": content}
        if error is not None:
            field_dict["fallback"] = Deserialization.BYTES.name
            field_dict["error"] = error
        return field_dict

    def dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "date": self.date,
            "headers": [(header.key, header.value_deserialized()) for header in self.headers],
            "key": self._field_dict(
                self.key_deserialization, self.key_deserialized(), self.key_error()
            ),
            "value": self._field_dict(
                self.value_deserialization, self.value_deserialized(), self.value_error()
            ),
        }

    def key_deserialized(self) -> Any:
        if self._key_deserialized is not _NOT_DESERIALIZED:
            return self._key_deserialized
        self._key_deserialized, self._key_error = self._deserialize_field(
            self.key, self.key_deserializer, self.key_deserialization, "key", MessageField.KEY
        )
        return self._key_deserialized

    def value_deserialized(self) -> Any:
        if self._value_deserialized is not _NOT_DESERIALIZED:
            return self._value_deserialized
        self._value_deserialized, self._value_error = self._deserialize_field(
            self.value,
            self.value_deserializer,
            self.value_deserialization,
            "value",
            MessageField.VALUE,
        )
        return self._value_deserialized

    def _deserialize_field(
        self,
        data: bytes | None,
        deserializer: Deserializer | None,
        requested: Deserialization,
        field_name: str,
        context: MessageField,
    ) -> tuple[Any, str | None]:
        if data is None:
            return None, None

        if deserializer is None:
            return str(data), None

        try:
            return deserializer.deserialize(data, self.topic, context), None
        except DESERIALIZATION_EXCEPTIONS as ex:
            logger.warning(
                "deserialization fallback topic=%s partition=%d offset=%d field=%s "
                "deserializer=%s error=%s",
                self.topic,
                self.partition,
                self.offset,
                field_name,
                requested,
                ex,
            )
            return str(data), str(ex)

    def key_error(self) -> str | None:
        self.key_deserialized()
        return self._key_error

    def value_error(self) -> str | None:
        self.value_deserialized()
        return self._value_error

    def has_deserialization_errors(self) -> bool:
        return self.key_error() is not None or self.value_error() is not None

    def key_str(self) -> str:
        return str(self.key_deserialized())

    def value_str(self) -> str:
        return str(self.value_deserialized())
