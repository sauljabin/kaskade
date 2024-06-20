from typing import Any, List


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
        return "{}:{}/{}".format(self.host, self.port, self.id)

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
    ) -> None:
        self.id = id
        self.client_id = client_id
        self.group = group
        self.host = host
        self.instance_id = instance_id

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(
            {
                "id": self.id,
                "group": self.group,
                "client_id": self.client_id,
                "host": self.host,
            }
        )

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
        return str(
            {
                "id": self.id,
                "group": self.group,
                "topic": self.topic,
                "offset": self.offset,
                "low": self.low,
                "high": self.high,
            }
        )

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
        broker: Node = Node(),
        state: str = "",
        partition_assignor: str = "",
        members: List[GroupMember] = None,
        partitions: List[GroupPartition] = None,
    ) -> None:
        if partitions is None:
            partitions = []
        if members is None:
            members = []
        self.broker = broker
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
        replicas: List[int] = None,
        isrs: List[int] = None,
        low: int = 0,
        high: int = 0,
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
        partitions: List[Partition] = None,
        groups: List[Group] = None,
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
        controller: Node = None,
        nodes: List[Node] = None,
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
