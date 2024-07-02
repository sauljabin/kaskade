import json
import struct
from enum import Enum, auto
from io import BytesIO
from typing import Any, Callable

import avro.schema
from avro.io import BinaryDecoder, DatumReader
from confluent_kafka.schema_registry import SchemaRegistryClient


MAGIC_BYTES = 0


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
        return sum([group.lag_count() for group in self.groups]) if self.groups is not None else 0

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
    BOOLEAN = auto()
    STRING = auto()
    LONG = auto()
    INTEGER = auto()
    DOUBLE = auto()
    FLOAT = auto()
    JSON = auto()
    AVRO = auto()

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


class DeserializerFactory:
    def __init__(self, schema_registry_config: dict[str, str] | None):
        if schema_registry_config:
            self.schema_registry_client = SchemaRegistryClient(schema_registry_config)

    def make_deserializer(self, deserialization_format: Format) -> Callable[[bytes], Any]:
        def avro_deserializer(raw_bytes: bytes) -> Any:
            if self.schema_registry_client is None:
                raise Exception("Schema Registry is not configured")

            magic, schema_id = struct.unpack(">bI", raw_bytes[:5])

            if magic != MAGIC_BYTES:
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


class Header:
    def __init__(
        self,
        key: str = "",
        value: bytes | None = None,
        value_deserializer: Callable[[bytes], Any] | None = None,
    ):
        self.key = key
        self.value = value
        self.value_deserializer = value_deserializer

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.key}:{self.value_str()}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Header):
            return self.key == other.key
        return False

    def value_deserialized(self) -> Any:
        if self.value is None:
            return

        if self.value_deserializer is None:
            return str(self.value)

        try:
            return self.value_deserializer(self.value)
        except Exception:
            # it doesn't matter to show the binaries
            return str(self.value)

    def value_str(self) -> str:
        return str(self.value_deserialized())


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
        key_deserializer: Callable[[bytes], Any] | None = None,
        value_deserializer: Callable[[bytes], Any] | None = None,
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
        self.key_deserializer = key_deserializer
        self.value_deserializer = value_deserializer

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
                [(header.key, header.value_deserialized()) for header in self.headers]
                if self.headers is not None
                else []
            ),
            "key format": self.key_format.name,
            "value format": self.value_format.name,
            "key": self.key_deserialized(),
            "value": self.value_deserialized(),
        }

    def key_deserialized(self) -> Any:
        if self.key is None:
            return

        if self.key_deserializer is None:
            return str(self.key)

        return self.key_deserializer(self.key)

    def value_deserialized(self) -> Any:
        if self.value is None:
            return

        if self.value_deserializer is None:
            return str(self.value)

        return self.value_deserializer(self.value)

    def key_str(self) -> str:
        return str(self.key_deserialized())

    def value_str(self) -> str:
        return str(self.value_deserialized())
