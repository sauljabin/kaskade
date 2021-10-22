from typing import List


class Broker:
    def __init__(self, id: int = -1, host: str = "", port: int = -1) -> None:
        self.id = id
        self.host = host
        self.port = port

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return "{}:{}/{}".format(self.host, self.port, self.id)


class Group:
    def __init__(
        self, id: str = "", broker: Broker = Broker(), state: str = "", members: int = 0
    ) -> None:
        self.broker = broker
        self.id = id
        self.state = state
        self.members = members

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.id


class Partition:
    def __init__(
        self,
        id: int = -1,
        leader: int = -1,
        replicas: List[int] = [],
        isrs: List[int] = [],
    ) -> None:
        self.id = id
        self.leader = leader
        self.replicas = replicas
        self.isrs = isrs

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self.id)


class Topic:
    def __init__(
        self,
        name: str = "",
        partitions: List[Partition] = [],
        groups: List[Group] = [],
    ) -> None:
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

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.name


class Cluster:
    def __init__(
        self,
        brokers: List[Broker] = [],
        version: str = "",
        has_schemas: bool = False,
        protocol: str = "plain",
    ) -> None:
        self.brokers = brokers
        self.version = version
        self.has_schemas = has_schemas
        self.protocol = protocol

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(
            {
                "brokers": [str(broker) for broker in self.brokers],
                "version": self.version,
                "has_schemas": self.has_schemas,
                "protocol": self.protocol,
            }
        )

    def brokers_count(self) -> int:
        return len(self.brokers) if self.brokers is not None else 0
