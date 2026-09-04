import math
from collections.abc import Mapping
from dataclasses import dataclass, fields

CONSUMER_POLL = "consumer.poll"
CONSUMER_IDLE = "consumer.idle"
CONSUMER_ASSIGNMENT = "consumer.assignment"
CONSUMER_REQUEST = "consumer.request"
ADMIN_READ = "admin.read"
ADMIN_WRITE = "admin.write"

TIMEOUT_PROPERTIES = (
    CONSUMER_POLL,
    CONSUMER_IDLE,
    CONSUMER_ASSIGNMENT,
    CONSUMER_REQUEST,
    ADMIN_READ,
    ADMIN_WRITE,
)


@dataclass(frozen=True)
class TimeoutConfig:
    """Kaskade operation deadlines, expressed in seconds."""

    consumer_poll: float = 0.5
    consumer_idle: float = 2.5
    consumer_assignment: float = 15.0
    consumer_request: float = 10.0
    admin_read: float = 10.0
    admin_write: float = 60.0

    @classmethod
    def from_dict(cls, config: Mapping[str, str]) -> "TimeoutConfig":
        unknown = sorted(set(config) - set(TIMEOUT_PROPERTIES))
        if unknown:
            raise ValueError(f"Unrecognized timeout properties: {', '.join(unknown)}")

        values: dict[str, float] = {}
        for property_name, raw_value in config.items():
            try:
                value = float(raw_value)
            except ValueError as ex:
                raise ValueError(f"{property_name} must be a number of seconds") from ex
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{property_name} must be greater than zero")
            values[property_name.replace(".", "_")] = value
        return cls(**values)

    def as_dict(self) -> dict[str, float]:
        return {field.name.replace("_", "."): getattr(self, field.name) for field in fields(self)}
