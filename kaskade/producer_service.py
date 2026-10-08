"""Produce single records and wait for the broker acknowledgement."""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from time import perf_counter
from typing import Any

from confluent_kafka import TIMESTAMP_NOT_AVAILABLE, KafkaError, KafkaException, Producer

from kaskade import logger
from kaskade.concurrency import run_blocking
from kaskade.serializers import Serialization
from kaskade.timeouts import TimeoutConfig

POLL_INTERVAL_SECONDS = 0.1
AUTHORIZATION_ERROR_CODES = frozenset(
    {
        KafkaError.CLUSTER_AUTHORIZATION_FAILED,
        KafkaError.SASL_AUTHENTICATION_FAILED,
        KafkaError.TOPIC_AUTHORIZATION_FAILED,
        KafkaError.TRANSACTIONAL_ID_AUTHORIZATION_FAILED,
    }
)
TIMEOUT_ERROR_CODES = frozenset(
    {
        KafkaError._MSG_TIMED_OUT,
        KafkaError._TIMED_OUT,
        KafkaError.REQUEST_TIMED_OUT,
    }
)


@dataclass(frozen=True)
class ProducerSettings:
    """The producer command's configuration."""

    topic: str
    kafka_config: dict[str, Any]
    key_serialization: Serialization = Serialization.STRING
    value_serialization: Serialization = Serialization.STRING
    partition: int | None = None
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)


@dataclass(frozen=True)
class OutgoingRecord:
    """Serialized record content; None is Kafka null, distinct from empty bytes."""

    key: bytes | None
    value: bytes | None
    headers: tuple[tuple[str, str | None], ...] = ()
    partition: int | None = None


@dataclass(frozen=True)
class Delivery:
    partition: int
    offset: int
    timestamp: datetime | None

    def summary(self) -> str:
        parts = ["Delivered", f"Partition {self.partition}", f"Offset {self.offset}"]
        if self.timestamp is not None:
            parts.append(self.timestamp.astimezone().strftime("%H:%M:%S.%f")[:-3])
        return " · ".join(parts)


class DeliveryFailure(Enum):
    AUTHORIZATION = auto()
    TIMEOUT = auto()
    BROKER = auto()

    def title(self) -> str:
        return {
            DeliveryFailure.AUTHORIZATION: "Authorization Error",
            DeliveryFailure.TIMEOUT: "Delivery Timeout",
            DeliveryFailure.BROKER: "Delivery Error",
        }[self]


class DeliveryError(Exception):
    """A record was not acknowledged; the message never contains record content."""

    def __init__(self, failure: DeliveryFailure, message: str) -> None:
        super().__init__(message)
        self.failure = failure


class DeliveryInProgressError(RuntimeError):
    """Raised when a second record is produced before the first is acknowledged."""


def delivery_error(error: KafkaError) -> DeliveryError:
    code = error.code()
    if code in AUTHORIZATION_ERROR_CODES:
        failure = DeliveryFailure.AUTHORIZATION
    elif code in TIMEOUT_ERROR_CODES:
        failure = DeliveryFailure.TIMEOUT
    else:
        failure = DeliveryFailure.BROKER
    return DeliveryError(failure, error.str())


class ProducerService:
    """Owns one confluent-kafka Producer; construction performs no network I/O."""

    def __init__(self, settings: ProducerSettings) -> None:
        self.settings = settings
        self.timeouts = settings.timeouts
        self._producer: Producer | None = None
        self._delivering = threading.Lock()
        self._closing = threading.Event()

    def start(self) -> None:
        """Create the client so configuration errors surface before the TUI opens."""
        if self._producer is None:
            self._producer = Producer(self.settings.kafka_config, logger=logger)

    @property
    def is_delivering(self) -> bool:
        return self._delivering.locked()

    async def produce(self, record: OutgoingRecord) -> Delivery:
        """Queue one record and return only after the broker acknowledges it."""
        if not self._delivering.acquire(blocking=False):
            raise DeliveryInProgressError("A record is already being delivered")
        try:
            return await run_blocking(self._produce, record)
        finally:
            self._delivering.release()

    def _produce(self, record: OutgoingRecord) -> Delivery:
        self.start()
        assert self._producer is not None
        outcome: list[tuple[KafkaError | None, Any]] = []

        def on_delivery(error: KafkaError | None, message: Any) -> None:
            outcome.append((error, message))

        produce_options: dict[str, Any] = {
            "key": record.key,
            "value": record.value,
            "headers": list(record.headers),
            "on_delivery": on_delivery,
        }
        if record.partition is not None:
            produce_options["partition"] = record.partition
        try:
            self._producer.produce(self.settings.topic, **produce_options)
        except BufferError as ex:
            raise DeliveryError(DeliveryFailure.BROKER, "The local producer queue is full") from ex
        except KafkaException as ex:
            raise delivery_error(ex.args[0]) from ex

        deadline = perf_counter() + self.timeouts.producer_delivery
        while not outcome:
            if self._closing.is_set():
                raise DeliveryError(
                    DeliveryFailure.TIMEOUT,
                    "Kaskade closed before the broker acknowledged the record",
                )
            remaining = deadline - perf_counter()
            if remaining <= 0:
                raise DeliveryError(
                    DeliveryFailure.TIMEOUT,
                    f"No broker acknowledgement within {self.timeouts.producer_delivery:g} "
                    "seconds; the record may still be delivered",
                )
            self._producer.poll(min(remaining, POLL_INTERVAL_SECONDS))

        error, message = outcome[0]
        if error is not None:
            raise delivery_error(error)
        return Delivery(message.partition(), message.offset(), _timestamp(message))

    def close(self) -> None:
        """Flush within the producer.flush deadline so shutdown never hangs."""
        self._closing.set()
        if self._producer is None:
            return
        undelivered = self._producer.flush(self.timeouts.producer_flush)
        if undelivered:
            logger.warning("%d record(s) were not delivered before shutdown", undelivered)
        self._producer = None

    async def aclose(self) -> None:
        self._closing.set()
        await run_blocking(self.close)


def _timestamp(message: Any) -> datetime | None:
    timestamp_type, milliseconds = message.timestamp()
    if timestamp_type == TIMESTAMP_NOT_AVAILABLE:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
