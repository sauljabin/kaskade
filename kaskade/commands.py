from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class CreateTopicCommand:
    name: str
    partitions: int
    replicas: int | None
    min_insync_replicas: int | None
    cleanup_policy: str
    retention_ms: int


@dataclass(frozen=True)
class ConfigChange:
    """A topic configuration change; a ``None`` value resets it to the cluster default."""

    name: str
    current: str
    value: str | None

    @property
    def reset(self) -> bool:
        return self.value is None


@dataclass(frozen=True)
class UpdateTopicCommand:
    """The changes an edit applies; ``partitions`` is set only when the count increases."""

    partitions: int | None = None
    configs: tuple[ConfigChange, ...] = ()

    @property
    def changed(self) -> bool:
        return self.partitions is not None or bool(self.configs)


class OffsetTarget(Enum):
    EARLIEST = "Earliest"
    LATEST = "Latest"
    TIMESTAMP = "Timestamp"
    OFFSET = "Offset"


@dataclass(frozen=True)
class ResetOffsetsCommand:
    """Reset a group's committed offsets for some partitions of a topic.

    ``value`` is the epoch milliseconds for ``TIMESTAMP`` and the offset for
    ``OFFSET``; the other targets ignore it.
    """

    group: str
    topic: str
    partitions: tuple[int, ...]
    target: OffsetTarget
    value: int = 0


@dataclass(frozen=True)
class RecordFilters:
    key: str = ""
    value: str = ""
    partition: int | None = None
    header: str = ""

    @property
    def active(self) -> bool:
        return bool(self.key or self.value or self.partition is not None or self.header)


EMPTY_RECORD_FILTERS = RecordFilters()
