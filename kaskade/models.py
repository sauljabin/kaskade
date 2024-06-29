import json
from enum import Enum, auto
from typing import Any

from confluent_kafka.serialization import (
    IntegerDeserializer,
    DoubleDeserializer,
    StringDeserializer,
    SerializationError,
)


class Node:
    def __init__(
        self,
        id: int = -1,
        host: str = "",
        port: int = -1,
        rack: str = "",
    ) -> None:
        self.id = id
        self.host = host
        self.port = port
        self.rack = rack

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.host}:{self.port}/{self.id}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Node):
            return self.id == other.id
        return False


class GroupMember:
    def __init__(
        self,
        id: str = "",
        client_id: str = "",
        group: str = "",
        host: str = "",
        instance_id: str = "",
        assignment: list[int] | None = None,
    ) -> None:
        self.id = id
        self.client_id = client_id
        self.group = group
        self.host = host
        self.instance_id = instance_id

        if assignment is None:
            assignment = []
        self.assignment = assignment

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self.id)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, GroupMember):
            return self.id == other.id
        return False


class GroupPartition:
    def __init__(
        self,
        id: int = -1,
        topic: str = "",
        group: str = "",
        offset: int = 0,
        low: int = 0,
        high: int = 0,
    ) -> None:
        self.id = id
        self.topic = topic
        self.group = group
        self.offset = offset
        self.low = low
        self.high = high

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self.id)

    def lag_count(self) -> int:
        if self.high < 0:
            return 0
        elif self.offset < 0:
            return self.high - self.low
        else:
            return self.high - self.offset

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, GroupPartition):
            return self.id == other.id
        return False


class Group:
    def __init__(
        self,
        id: str = "",
        coordinator: None | Node = None,
        state: str = "",
        partition_assignor: str = "",
        members: None | list[GroupMember] = None,
        partitions: None | list[GroupPartition] = None,
    ) -> None:
        if partitions is None:
            partitions = []
        if members is None:
            members = []
        self.coordinator = coordinator
        self.id = id
        self.state = state
        self.partition_assignor = partition_assignor
        self.members = members
        self.partitions = partitions

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.id

    def lag_count(self) -> int:
        return (
            sum([partition.lag_count() for partition in self.partitions])
            if self.partitions is not None
            else 0
        )

    def members_count(self) -> int:
        return len(self.members) if self.members is not None else 0

    def partitions_count(self) -> int:
        return len(self.partitions) if self.partitions is not None else 0

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Group):
            return self.id == other.id
        return False


class Partition:
    def __init__(
        self,
        id: int = -1,
        leader: int = -1,
        replicas: None | list[int] = None,
        isrs: None | list[int] = None,
        low: int = 0,
        high: int = 0,
        topic: str = "",
    ) -> None:
        if isrs is None:
            isrs = []
        if replicas is None:
            replicas = []
        self.id = id
        self.leader = leader
        self.replicas = replicas
        self.isrs = isrs
        self.low = low
        self.high = high
        self.topic = topic

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self.id)

    def messages_count(self) -> int:
        return self.high - self.low

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Partition):
            return self.id == other.id
        return False


class Topic:
    def __init__(
        self,
        name: str = "",
        partitions: None | list[Partition] = None,
        groups: None | list[Group] = None,
    ) -> None:
        if groups is None:
            groups = []
        if partitions is None:
            partitions = []
        self.name = name
        self.partitions = partitions
        self.groups = groups

    def partitions_count(self) -> int:
        return len(self.partitions) if self.partitions is not None else 0

    def groups_count(self) -> int:
        return len(self.groups) if self.groups is not None else 0

    def group_members_count(self) -> int:
        return (
            sum([group.members_count() for group in self.groups]) if self.groups is not None else 0
        )

    def replicas_count(self) -> int:
        return (
            max([len(partition.replicas) for partition in self.partitions], default=0)
            if self.partitions is not None
            else 0
        )

    def isrs_count(self) -> int:
        return (
            min([len(partition.isrs) for partition in self.partitions], default=0)
            if self.partitions is not None
            else 0
        )

    def lag(self) -> int:
        return (
            max([group.lag_count() for group in self.groups], default=0)
            if self.groups is not None
            else 0
        )

    def records_count(self) -> int:
        return (
            sum([partition.messages_count() for partition in self.partitions])
            if self.partitions is not None
            else 0
        )

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Topic):
            return self.name == other.name
        return False


class Cluster:
    def __init__(
        self,
        id: str = "",
        controller: None | Node = None,
        nodes: None | list[Node] = None,
    ) -> None:
        if nodes is None:
            nodes = []
        self.id = id
        self.controller = controller
        self.nodes = nodes

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Cluster):
            return self.id == other.id
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


class Format(Enum):
    BYTES = auto()
    STRING = auto()
    INTEGER = auto()
    DOUBLE = auto()
    JSON = auto()

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


def _deserialize(deserialization_format: Format, value: bytes | None) -> Any:
    if value is None:
        return

    match deserialization_format:
        case Format.STRING:
            deserializer = StringDeserializer()
        case Format.JSON:
            deserializer = json.loads
        case Format.INTEGER:
            deserializer = IntegerDeserializer()
        case Format.DOUBLE:
            deserializer = DoubleDeserializer()
        case _:
            deserializer = str

    return deserializer(value)


class Header:
    def __init__(self, key: str = "", value: bytes | None = None):
        self.key = key
        self.value = value

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.key}:{self.value_str()}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Header):
            return self.key == other.key
        return False

    def value_str(self) -> str:
        try:
            deserializer = StringDeserializer()
            return str(deserializer(self.value))
        except SerializationError:
            return str(self.value)


class Record:
    def __init__(
        self,
        topic: str = "",
        partition: int = -1,
        offset: int = -1,
        date: str = "",
        key: bytes | None = None,
        value: bytes | None = None,
        headers: list[Header] | None = None,
        key_format: Format = Format.BYTES,
        value_format: Format = Format.BYTES,
    ) -> None:
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.date = date
        self.key = key
        self.value = value
        if headers is None:
            headers = []
        self.headers = headers
        self.key_format = key_format
        self.value_format = value_format

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.partition}/{self.offset}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Record):
            return self.partition == other.partition and self.offset == other.offset
        return False

    def headers_count(self) -> int:
        return len(self.headers) if self.headers is not None else 0

    def dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "date": self.date,
            "headers": (
                {header.key: header.value_str() for header in self.headers}
                if self.headers is not None
                else {}
            ),
            "key format": self.key_format.name,
            "value format": self.value_format.name,
            "key": _deserialize(self.key_format, self.key),
            "value": _deserialize(self.value_format, self.value),
        }

    def key_str(self) -> str:
        return str(_deserialize(self.key_format, self.key))

    def value_str(self) -> str:
        return str(_deserialize(self.value_format, self.value))
