from dataclasses import dataclass


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
