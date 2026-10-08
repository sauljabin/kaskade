import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import ceil
from time import perf_counter
from typing import Any

from confluent_kafka import (
    OFFSET_BEGINNING,
    OFFSET_END,
    Consumer,
    KafkaError,
    KafkaException,
    TopicPartition,
)
from confluent_kafka.serialization import MessageField

from kaskade import logger
from kaskade.commands import EMPTY_RECORD_FILTERS, RecordFilters
from kaskade.concurrency import run_blocking
from kaskade.configs import (
    AUTO_OFFSET_RESET,
    EARLIEST,
    ENABLE_AUTO_COMMIT,
    GROUP_ID,
    MAX_POLL_INTERVAL_MS,
    MILLISECONDS_24H,
)
from kaskade.deserializers import BytesEncoding, Deserialization, DeserializerPool
from kaskade.models import (
    Header,
    PartitionOffset,
    PartitionSelection,
    Record,
)
from kaskade.timeouts import TimeoutConfig

CONSUMER_AUTHORIZATION_ERROR_CODES = frozenset(
    {
        KafkaError.GROUP_AUTHORIZATION_FAILED,
        KafkaError.SASL_AUTHENTICATION_FAILED,
        KafkaError.TOPIC_AUTHORIZATION_FAILED,
    }
)


class PartitionSelectionError(ValueError):
    """Raised when an explicit partition or offset cannot be assigned."""


@dataclass(frozen=True)
class ConsumerSettings:
    """The consumer command's configuration, shared by every consumer built for it."""

    topic: str
    kafka_config: dict[str, Any]
    key_deserialization: Deserialization
    value_deserialization: Deserialization
    registry_config: dict[str, str] = field(default_factory=dict)
    protobuf_config: dict[str, str] = field(default_factory=dict)
    avro_config: dict[str, str] = field(default_factory=dict)
    json_config: dict[str, str] = field(default_factory=dict)
    bytes_config: dict[str, str] = field(default_factory=dict)
    fallback_config: dict[str, str] = field(default_factory=dict)
    partitions: tuple[PartitionSelection, ...] = ()
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)

    def deserializer_pool(self) -> DeserializerPool:
        return DeserializerPool(
            self.registry_config,
            self.protobuf_config,
            self.avro_config,
            self.json_config,
        )


class ConsumerService:
    def __init__(
        self,
        settings: ConsumerSettings,
        deserializer_pool: DeserializerPool,
        *,
        page_size: int = 25,
    ) -> None:
        self.settings = settings
        self.topic = settings.topic
        self.page_size = page_size
        self.timeouts = settings.timeouts
        self.key_deserialization = settings.key_deserialization
        self.value_deserialization = settings.value_deserialization
        self.key_bytes_encoding = BytesEncoding.from_config(settings.bytes_config, MessageField.KEY)
        self.value_bytes_encoding = BytesEncoding.from_config(
            settings.bytes_config, MessageField.VALUE
        )
        self.fallback_bytes_encoding = BytesEncoding.from_config(settings.fallback_config)
        self.partitions = settings.partitions
        kafka_config = settings.kafka_config
        self.manually_assigned = (
            bool(self.partitions) or kafka_config.get(AUTO_OFFSET_RESET) == EARLIEST
        )
        self.stable = False
        self.started_at = perf_counter()
        self.assigned_at: float | None = None
        self._consumer_error: KafkaError | None = None
        default_group_id = f"kaskade-{uuid.uuid4().hex[:8]}"
        consumer_config = kafka_config | {
            ENABLE_AUTO_COMMIT: False,
            MAX_POLL_INTERVAL_MS: MILLISECONDS_24H,
            "error_cb": self._on_consumer_error,
        }
        consumer_config.setdefault(GROUP_ID, default_group_id)
        self.group_id = str(consumer_config[GROUP_ID])
        self.consumer = Consumer(consumer_config, logger=logger)
        self.started = False
        try:
            self.deserializer_pool = deserializer_pool
            self.key_deserializer = deserializer_pool.get(self.key_deserialization)
            self.value_deserializer = deserializer_pool.get(self.value_deserialization)
            self.header_deserializer = deserializer_pool.get(Deserialization.STRING)
        except Exception:
            self.consumer.close()
            raise
        self._operation_lock = asyncio.Lock()

    def start(self) -> None:
        """Subscribe or assign partitions; this may block on topic metadata and watermarks."""
        if self.started:
            return
        self._start_consuming()
        self.started = True

    def _start_consuming(self) -> None:
        if not self.manually_assigned:
            self.consumer.subscribe([self.topic], on_assign=self.on_assign)
            return

        available_partitions = self._available_partitions()
        selections = self.partitions or tuple(
            PartitionSelection(partition, PartitionOffset.EARLIEST)
            for partition in sorted(available_partitions)
        )
        assignments = [
            self._assignment(selection, available_partitions) for selection in selections
        ]
        self.consumer.assign(assignments)
        self.on_assign(self.consumer, assignments)

    def _available_partitions(self) -> set[int]:
        metadata = self.consumer.list_topics(self.topic, timeout=self.timeouts.consumer_request)
        topic_metadata = metadata.topics.get(self.topic)
        if topic_metadata is None:
            raise PartitionSelectionError(f"Topic {self.topic!r} does not exist")
        if topic_metadata.error is not None:
            raise KafkaException(topic_metadata.error)
        return set(topic_metadata.partitions)

    def _assignment(
        self,
        selection: PartitionSelection,
        available_partitions: set[int],
    ) -> TopicPartition:
        if selection.partition not in available_partitions:
            raise PartitionSelectionError(
                f"Partition {selection.partition} does not exist in topic {self.topic!r}"
            )

        offset = self._assignment_offset(selection)
        if isinstance(selection.offset, int):
            low, high = self.consumer.get_watermark_offsets(
                TopicPartition(self.topic, selection.partition),
                timeout=self.timeouts.consumer_request,
                cached=False,
            )
            if not low <= selection.offset <= high:
                raise PartitionSelectionError(
                    f"Offset {selection.offset} is out of range for partition "
                    f"{selection.partition}; available offsets are {low} through {high}"
                )
        return TopicPartition(self.topic, selection.partition, offset)

    @staticmethod
    def _assignment_offset(selection: PartitionSelection) -> int:
        if selection.offset is PartitionOffset.EARLIEST:
            return OFFSET_BEGINNING
        if selection.offset is None:
            return OFFSET_END
        return selection.offset

    def on_assign(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        self.stable = True
        self.assigned_at = perf_counter()
        logger.info(
            "consumer assigned topic=%s partitions=%d elapsed=%.3fs",
            self.topic,
            len(partitions),
            self.assigned_at - self.started_at,
        )

    def _on_consumer_error(self, error: KafkaError) -> None:
        logger.error("consumer error: %s", error)
        if error.code() in CONSUMER_AUTHORIZATION_ERROR_CODES:
            self._consumer_error = error

    def _raise_consumer_error(self) -> None:
        if self._consumer_error is None:
            return
        error = self._consumer_error
        self._consumer_error = None
        raise KafkaException(error)

    def close(self) -> None:
        try:
            if self.manually_assigned:
                self.consumer.unassign()
            else:
                self.consumer.unsubscribe()
        finally:
            self.consumer.close()

    async def aclose(self) -> None:
        async with self._operation_lock:
            await run_blocking(self.close)

    async def consume(
        self,
        *,
        filters: RecordFilters = EMPTY_RECORD_FILTERS,
    ) -> list[Record]:
        async with self._operation_lock:
            return await self._consume(filters)

    async def _consume(self, filters: RecordFilters) -> list[Record]:
        if not self.started:
            await run_blocking(self.start)
        chunk_started_at = perf_counter()
        records: list[Record] = []
        poll_retries = 0
        stabilization_retries = 0
        max_poll_retries = max(1, ceil(self.timeouts.consumer_idle / self.timeouts.consumer_poll))
        max_stabilization_retries = max(
            1,
            ceil(self.timeouts.consumer_assignment / self.timeouts.consumer_poll),
        )
        scanned_records = 0
        first_record_at: float | None = None

        while (
            len(records) < self.page_size
            and poll_retries < max_poll_retries
            and stabilization_retries < max_stabilization_retries
        ):
            record_batch = await run_blocking(
                self.consumer.consume,
                self.page_size - len(records),
                timeout=self.timeouts.consumer_poll,
            )
            self._raise_consumer_error()

            if not self.stable:
                stabilization_retries += 1
                continue
            stabilization_retries = 0

            if not record_batch:
                poll_retries += 1
                continue
            poll_retries = 0

            if first_record_at is None:
                first_record_at = perf_counter()
            matched, scanned = await run_blocking(
                self._records_from_batch,
                record_batch,
                filters,
                self.page_size - len(records),
            )
            records.extend(matched)
            scanned_records += scanned

        logger.info(
            "consumer chunk completed topic=%s scanned=%d matched=%d first_record=%.3fs "
            "elapsed=%.3fs",
            self.topic,
            scanned_records,
            len(records),
            first_record_at - chunk_started_at if first_record_at is not None else -1,
            perf_counter() - chunk_started_at,
        )

        return records

    def _records_from_batch(
        self,
        messages: list[Any],
        filters: RecordFilters,
        limit: int,
    ) -> tuple[list[Record], int]:
        """Convert and filter one polled batch in a single worker-thread call.

        Returns the matching records, at most ``limit``, and how many messages were
        scanned; messages after the limit is reached are neither deserialized nor scanned.
        """
        records: list[Record] = []
        scanned = 0
        for message in messages:
            scanned += 1
            record = self._record_from_message(message)
            if self._matches(record, filters):
                records.append(record)
                if len(records) >= limit:
                    break
        return records, scanned

    def _record_from_message(self, message: Any) -> Record:
        if message.error():
            raise KafkaException(message.error())
        record = Record(
            topic=self.topic,
            partition=message.partition(),
            offset=message.offset(),
            key=message.key(),
            value=message.value(),
            timestamp=self._message_timestamp(message),
            headers=[
                Header(
                    key=key,
                    value=value,
                    value_deserializer=self.header_deserializer,
                    fallback_bytes_encoding=self.fallback_bytes_encoding,
                    value_deserialization=Deserialization.STRING,
                )
                for key, value in message.headers() or []
            ],
            key_deserialization=self.key_deserialization,
            value_deserialization=self.value_deserialization,
            key_deserializer=self.key_deserializer,
            value_deserializer=self.value_deserializer,
            key_bytes_encoding=self.key_bytes_encoding,
            value_bytes_encoding=self.value_bytes_encoding,
            fallback_bytes_encoding=self.fallback_bytes_encoding,
        )
        record.resolve_deserializations()
        self._log_deserialization_fallbacks(record)
        return record

    def _log_deserialization_fallbacks(self, record: Record) -> None:
        for field_name, outcome in (
            ("key", record.key_outcome()),
            ("value", record.value_outcome()),
        ):
            if outcome.error is None:
                continue
            logger.warning(
                "record deserialization fallback topic=%s partition=%d offset=%d "
                "field=%s requested=%s fallback=%s encoding=%s error=%s",
                record.topic,
                record.partition,
                record.offset,
                field_name,
                outcome.requested.name,
                Deserialization.BYTES.name,
                outcome.bytes_encoding.name,
                outcome.error,
            )

    @staticmethod
    def _message_timestamp(message: Any) -> datetime | None:
        timestamp_available, timestamp = message.timestamp()
        if timestamp_available <= 0:
            return None
        return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

    @staticmethod
    def _matches(
        record: Record,
        filters: RecordFilters,
    ) -> bool:
        if filters.partition is not None and record.partition != filters.partition:
            return False
        if filters.key and filters.key not in record.key_str():
            return False
        if filters.value and filters.value not in record.value_str():
            return False
        return not filters.header or any(
            filters.header in header.value_str() for header in record.headers
        )
