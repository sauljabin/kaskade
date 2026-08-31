from dataclasses import dataclass


@dataclass(frozen=True)
class PartitionSelection:
    """A single partition and its starting offset, as requested through the CLI.

    ``offset`` is ``None`` for the default/latest position, the string
    ``kaskade.configs.EARLIEST`` for Kafka's earliest sentinel, or a
    non-negative absolute offset.
    """

    partition: int
    offset: int | str | None = None


@dataclass(frozen=True)
class CreateTopicCommand:
    name: str
    partitions: int
    replicas: int
    min_insync_replicas: int
    cleanup_policy: str
    retention_ms: int


@dataclass(frozen=True)
class UpdateTopicCommand:
    partitions: int
    min_insync_replicas: int
    cleanup_policy: str
    retention_ms: int


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
