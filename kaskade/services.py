import asyncio
import functools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, cast

from confluent_kafka import (
    OFFSET_BEGINNING,
    OFFSET_END,
    OFFSET_INVALID,
    Consumer,
    ConsumerGroupTopicPartitions,
    KafkaException,
    TopicPartition,
)
from confluent_kafka.admin import (
    AdminClient,
    AlterConfigOpType,
    ConfigEntry,
    ConfigResource,
    ConfigSource,
    ConsumerGroupDescription,
    OffsetSpec,
    ResourceType,
    TopicMetadata,
)
from confluent_kafka.cimpl import NewPartitions, NewTopic

from kaskade import logger
from kaskade.commands import EMPTY_RECORD_FILTERS, CreateTopicCommand, RecordFilters
from kaskade.configs import (
    CLEANUP_POLICY_CONFIG,
    ENABLE_AUTO_COMMIT,
    GROUP_ID,
    MAX_POLL_INTERVAL_MS,
    MILLISECONDS_24H,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
)
from kaskade.deserializers import Deserialization, DeserializerPool
from kaskade.models import (
    Group,
    GroupMember,
    GroupPartition,
    Header,
    MetricState,
    Node,
    Partition,
    PartitionOffset,
    PartitionSelection,
    Record,
    Topic,
    TopicConfiguration,
)
from kaskade.utils import make_it_async

ADMIN_EXCEPTIONS: tuple[type[Exception], ...] = (
    KafkaException,
    RuntimeError,
    TypeError,
    ValueError,
)


class PartitionSelectionError(ValueError):
    """Raised when an explicit partition or offset cannot be assigned."""


class ConsumerService:
    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, Any],
        deserializer_factory: DeserializerPool,
        key_deserialization: Deserialization,
        value_deserialization: Deserialization,
        *,
        partitions: tuple[PartitionSelection, ...] = (),
        page_size: int = 25,
        poll_retries: int = 5,
        timeout: float = 0.5,
        stabilization_retries: int = 30,
    ) -> None:
        self.topic = topic
        self.page_size = page_size
        self.poll_retries = poll_retries
        self.stabilization_retries = stabilization_retries
        self.timeout = timeout
        self.key_deserialization = key_deserialization
        self.value_deserialization = value_deserialization
        self.partitions = partitions
        self.stable = False
        self.started_at = perf_counter()
        self.assigned_at: float | None = None
        self.consumer = Consumer(
            kafka_config
            | {
                GROUP_ID: f"kaskade-{uuid.uuid4()}",
                ENABLE_AUTO_COMMIT: False,
                MAX_POLL_INTERVAL_MS: MILLISECONDS_24H,
            },
            logger=logger,
        )
        try:
            self._start_consuming()
            self.deserializer_factory = deserializer_factory
            self.key_deserializer = deserializer_factory.get(key_deserialization)
            self.value_deserializer = deserializer_factory.get(value_deserialization)
            self.header_deserializer = deserializer_factory.get(Deserialization.STRING)
        except Exception:
            self.consumer.close()
            raise
        self._operation_lock = asyncio.Lock()

    def _start_consuming(self) -> None:
        if not self.partitions:
            self.consumer.subscribe([self.topic], on_assign=self.on_assign)
            return

        available_partitions = self._available_partitions()
        assignments = [
            self._assignment(selection, available_partitions) for selection in self.partitions
        ]
        self.consumer.assign(assignments)
        self.on_assign(self.consumer, assignments)

    def _available_partitions(self) -> set[int]:
        metadata = self.consumer.list_topics(self.topic, timeout=self.timeout)
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
                timeout=self.timeout,
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

    def close(self) -> None:
        if self.partitions:
            self.consumer.unassign()
        else:
            self.consumer.unsubscribe()
        self.consumer.close()

    async def aclose(self) -> None:
        async with self._operation_lock:
            await make_it_async(self.close)

    async def consume(
        self,
        *,
        filters: RecordFilters = EMPTY_RECORD_FILTERS,
    ) -> list[Record]:
        async with self._operation_lock:
            return await self._consume(filters)

    async def _consume(self, filters: RecordFilters) -> list[Record]:
        chunk_started_at = perf_counter()
        records: list[Record] = []
        poll_retries = 0
        stabilization_retries = 0
        scanned_records = 0
        first_record_at: float | None = None

        while (
            len(records) < self.page_size
            and poll_retries < self.poll_retries
            and stabilization_retries < self.stabilization_retries
        ):
            record_batch = await self._consume_batch(
                self.consumer.consume,
                self.page_size - len(records),
                timeout=self.timeout,
            )

            if not self.stable:
                stabilization_retries += 1
                continue
            stabilization_retries = 0

            if not record_batch:
                poll_retries += 1
                continue
            poll_retries = 0

            for record_metadata in record_batch:
                scanned_records += 1
                if first_record_at is None:
                    first_record_at = perf_counter()
                record = self._record_from_message(record_metadata)
                if self._matches(record, filters):
                    records.append(record)
                if len(records) >= self.page_size:
                    break

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

    @staticmethod
    async def _consume_batch(func: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            await future
            raise

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
                Header(key=key, value=value, value_deserializer=self.header_deserializer)
                for key, value in message.headers() or []
            ],
            key_deserialization=self.key_deserialization,
            value_deserialization=self.value_deserialization,
            key_deserializer=self.key_deserializer,
            value_deserializer=self.value_deserializer,
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
                "field=%s requested=%s fallback=%s error=%s",
                record.topic,
                record.partition,
                record.offset,
                field_name,
                outcome.requested.name,
                Deserialization.BYTES.name,
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


@dataclass(frozen=True)
class EnrichmentResult:
    errors: tuple[Exception, ...] = ()

    @property
    def successful(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class GroupSnapshot:
    descriptions: tuple[ConsumerGroupDescription, ...] = ()
    offsets: dict[str, tuple[TopicPartition, ...]] = field(default_factory=dict)
    errors: tuple[Exception, ...] = ()

    def offsets_for(self, group_id: str) -> tuple[TopicPartition, ...]:
        return self.offsets.get(group_id, ())


class TopicService:
    GROUP_OFFSET_CONCURRENCY = 16

    def __init__(self, config: dict[str, Any], *, timeout: float = 2.0) -> None:
        self.timeout = timeout
        self.config = config.copy()
        self.admin_client = AdminClient(self.config, logger=logger)

    def create(self, command: CreateTopicCommand) -> None:
        topic_config = {
            CLEANUP_POLICY_CONFIG: command.cleanup_policy,
            RETENTION_MS_CONFIG: str(command.retention_ms),
        }
        if command.min_insync_replicas is not None:
            topic_config[MIN_INSYNC_REPLICAS_CONFIG] = str(command.min_insync_replicas)

        new_topic = NewTopic(
            topic=command.name,
            num_partitions=command.partitions,
            replication_factor=command.replicas if command.replicas is not None else -1,
            config=topic_config,
        )
        futures = self.admin_client.create_topics([new_topic])
        for future in futures.values():
            future.result()

    def get_configs(self, name: str) -> dict[str, str]:
        return {config.name: cast(str, config.value) for config in self._config_entries(name)}

    def describe_configs(self, name: str) -> tuple[TopicConfiguration, ...]:
        configurations = (
            TopicConfiguration(
                name=config.name,
                value=cast(str, config.value),
            )
            for config in self._config_entries(name)
        )
        return tuple(configurations)

    def _config_entries(self, name: str) -> list[ConfigEntry]:
        resource = ConfigResource(ResourceType.TOPIC, name)
        futures = self.admin_client.describe_configs([resource])
        for future in futures.values():
            configs = future.result()
            return list(configs.values())
        return []

    def edit(self, name: str, config: dict[str, str]) -> None:
        entries = [
            ConfigEntry(
                name=key,
                value=value,
                source=ConfigSource.DYNAMIC_TOPIC_CONFIG,
                incremental_operation=AlterConfigOpType.SET,
            )
            for key, value in config.items()
        ]

        resource = ConfigResource(ResourceType.TOPIC, name=name, incremental_configs=entries)

        futures = self.admin_client.incremental_alter_configs([resource])
        for future in futures.values():
            future.result()

    def add_partitions(self, name: str, partitions: int) -> None:
        futures = self.admin_client.create_partitions(
            [NewPartitions(name, partitions)], request_timeout=self.timeout, validate_only=False
        )
        for future in futures.values():
            future.result()

    def delete(self, name: str) -> None:
        futures = self.admin_client.delete_topics([name])
        for future in futures.values():
            future.result()

    async def metadata(self) -> dict[str, Topic]:
        started_at = perf_counter()
        topics_metadata = await make_it_async(self._list_topics_metadata)
        topics = self._map_topics(topics_metadata)
        logger.info(
            "admin metadata loaded topics=%d partitions=%d elapsed=%.3fs",
            len(topics),
            sum(topic.partitions_count() for topic in topics.values()),
            perf_counter() - started_at,
        )
        return topics

    async def enrich_offsets(self, topics: dict[str, Topic]) -> EnrichmentResult:
        started_at = perf_counter()
        partitions = self._partition_lookup(topics)
        if not partitions:
            self._set_records_state(topics, MetricState.READY)
            return EnrichmentResult()

        earliest, latest, errors = await self._load_partition_offsets(tuple(partitions))
        self._apply_partition_offsets(topics, earliest, latest)
        logger.info(
            "admin offsets loaded partitions=%d errors=%d elapsed=%.3fs",
            len(partitions),
            len(errors),
            perf_counter() - started_at,
        )
        return EnrichmentResult(errors)

    async def _load_partition_offsets(self, partitions: tuple[TopicPartition, ...]) -> tuple[
        dict[tuple[str, int], int],
        dict[tuple[str, int], int],
        tuple[Exception, ...],
    ]:
        try:
            earliest_futures = self.admin_client.list_offsets(
                {
                    topic_partition: OffsetSpec.earliest()  # type: ignore[no-untyped-call]
                    for topic_partition in partitions
                },
                request_timeout=self.timeout,
            )
            latest_futures = self.admin_client.list_offsets(
                {
                    topic_partition: OffsetSpec.latest()  # type: ignore[no-untyped-call]
                    for topic_partition in partitions
                },
                request_timeout=self.timeout,
            )
        except ADMIN_EXCEPTIONS as ex:
            logger.error("admin offset request failed: %s", ex)
            return {}, {}, (ex,)

        earliest_result, latest_result = await asyncio.gather(
            self._resolve_offset_futures(earliest_futures),
            self._resolve_offset_futures(latest_futures),
        )
        earliest, earliest_errors = earliest_result
        latest, latest_errors = latest_result
        return earliest, latest, (*earliest_errors, *latest_errors)

    @staticmethod
    def _apply_partition_offsets(
        topics: dict[str, Topic],
        earliest: dict[tuple[str, int], int],
        latest: dict[tuple[str, int], int],
    ) -> None:
        for topic in topics.values():
            topic_offsets = [
                (
                    partition,
                    earliest.get((topic.name, partition.id)),
                    latest.get((topic.name, partition.id)),
                )
                for partition in topic.partitions
            ]
            if any(low is None or high is None for _, low, high in topic_offsets):
                if topic.records_state is not MetricState.READY:
                    topic.records_state = MetricState.UNAVAILABLE
            else:
                for partition, low, high in topic_offsets:
                    if low is not None and high is not None:
                        partition.low = low
                        partition.high = high
                topic.records_state = MetricState.READY

    @staticmethod
    def _set_records_state(topics: dict[str, Topic], state: MetricState) -> None:
        for topic in topics.values():
            if topic.records_state is not MetricState.READY:
                topic.records_state = state

    @staticmethod
    def _partition_lookup(topics: dict[str, Topic]) -> dict[TopicPartition, Partition]:
        return {
            TopicPartition(topic.name, partition.id): partition
            for topic in topics.values()
            for partition in topic.partitions
        }

    async def _resolve_offset_futures(
        self, futures: dict[TopicPartition, Any]
    ) -> tuple[dict[tuple[str, int], int], tuple[Exception, ...]]:
        async def resolve(
            topic_partition: TopicPartition, future: Any
        ) -> tuple[TopicPartition, int | None, Exception | None]:
            try:
                result = await asyncio.wrap_future(future)
                return topic_partition, result.offset, None
            except ADMIN_EXCEPTIONS as ex:
                logger.error("admin partition offset failed for %s: %s", topic_partition, ex)
                return topic_partition, None, ex

        resolved = await asyncio.gather(
            *(resolve(topic_partition, future) for topic_partition, future in futures.items())
        )
        offsets = {
            (str(topic_partition.topic), topic_partition.partition): offset
            for topic_partition, offset, error in resolved
            if error is None and offset is not None
        }
        errors = tuple(error for _, _, error in resolved if error is not None)
        return offsets, errors

    async def load_groups(self) -> GroupSnapshot:
        started_at = perf_counter()
        group_ids, list_errors = await self._list_group_ids()
        if not group_ids:
            return GroupSnapshot(errors=list_errors)

        descriptions, description_errors = await self._load_group_descriptions(group_ids)
        offsets, offset_errors = await self._load_group_offsets(group_ids)
        errors = (*list_errors, *description_errors, *offset_errors)
        logger.info(
            "admin groups loaded groups=%d errors=%d elapsed=%.3fs",
            len(group_ids),
            len(errors),
            perf_counter() - started_at,
        )
        return GroupSnapshot(descriptions, offsets, errors)

    async def _list_group_ids(self) -> tuple[tuple[str, ...], tuple[Exception, ...]]:
        try:
            list_result = await asyncio.wrap_future(
                self.admin_client.list_consumer_groups(request_timeout=self.timeout)
            )
        except ADMIN_EXCEPTIONS as ex:
            logger.error("admin consumer-group listing failed: %s", ex)
            return (), (ex,)
        return (
            tuple(group.group_id for group in list_result.valid or []),
            tuple(list_result.errors or ()),
        )

    async def _load_group_descriptions(
        self, group_ids: tuple[str, ...]
    ) -> tuple[tuple[ConsumerGroupDescription, ...], tuple[Exception, ...]]:
        descriptions: list[ConsumerGroupDescription] = []
        description_futures = self.admin_client.describe_consumer_groups(
            list(group_ids), request_timeout=self.timeout
        )
        description_results = await asyncio.gather(
            *(self._resolve_future(future) for future in description_futures.values())
        )
        errors: list[Exception] = []
        for description, error in description_results:
            if error is not None:
                errors.append(error)
            elif description is not None:
                descriptions.append(description)
        return tuple(descriptions), tuple(errors)

    async def _load_group_offsets(
        self, group_ids: tuple[str, ...]
    ) -> tuple[dict[str, tuple[TopicPartition, ...]], tuple[Exception, ...]]:
        semaphore = asyncio.Semaphore(self.GROUP_OFFSET_CONCURRENCY)
        offset_results = await asyncio.gather(
            *(self._load_single_group_offsets(group_id, semaphore) for group_id in group_ids)
        )
        offsets: dict[str, tuple[TopicPartition, ...]] = {}
        errors: list[Exception] = []
        for group_id, topic_partitions, error in offset_results:
            if error is not None:
                logger.error("admin consumer-group offsets failed for %s: %s", group_id, error)
                errors.append(error)
            else:
                offsets[group_id] = topic_partitions
        return offsets, tuple(errors)

    async def _load_single_group_offsets(
        self, group_id: str, semaphore: asyncio.Semaphore
    ) -> tuple[str, tuple[TopicPartition, ...], Exception | None]:
        async with semaphore:
            try:
                futures = self.admin_client.list_consumer_group_offsets(
                    [ConsumerGroupTopicPartitions(group_id)],
                    request_timeout=self.timeout,
                )
                result = await asyncio.wrap_future(futures[group_id])
                topic_partitions = tuple(result.topic_partitions or ())
                error = self._first_partition_error(topic_partitions)
                return group_id, () if error else topic_partitions, error
            except ADMIN_EXCEPTIONS as ex:
                return group_id, (), ex

    @staticmethod
    def _first_partition_error(partitions: tuple[TopicPartition, ...]) -> Exception | None:
        partition = next((item for item in partitions if item.error is not None), None)
        return KafkaException(partition.error) if partition is not None else None

    async def _resolve_future(self, future: Any) -> tuple[Any | None, Exception | None]:
        try:
            return await asyncio.wrap_future(future), None
        except ADMIN_EXCEPTIONS as ex:
            logger.error("admin request failed: %s", ex)
            return None, ex

    def apply_groups(self, topics: dict[str, Topic], snapshot: GroupSnapshot) -> EnrichmentResult:
        if snapshot.errors:
            self._set_groups_unavailable(topics)
            return EnrichmentResult(snapshot.errors)

        self._reset_groups(topics)
        partitions = self._partitions_by_key(topics)

        for group_metadata in snapshot.descriptions:
            committed_by_topic = self._committed_by_topic(group_metadata, snapshot, topics)
            for topic_name, committed in committed_by_topic.items():
                group = self._map_group(group_metadata, topic_name, committed, partitions)
                if group.partitions:
                    topics[topic_name].groups.append(group)

        return EnrichmentResult()

    @staticmethod
    def _set_groups_unavailable(topics: dict[str, Topic]) -> None:
        for topic in topics.values():
            if topic.groups_state is not MetricState.READY:
                topic.groups_state = MetricState.UNAVAILABLE

    @staticmethod
    def _reset_groups(topics: dict[str, Topic]) -> None:
        for topic in topics.values():
            topic.groups = []
            topic.groups_state = (
                MetricState.READY
                if topic.records_state is MetricState.READY
                else MetricState.UNAVAILABLE
            )

    @staticmethod
    def _partitions_by_key(topics: dict[str, Topic]) -> dict[tuple[str, int], Partition]:
        return {
            (topic.name, partition.id): partition
            for topic in topics.values()
            for partition in topic.partitions
        }

    @staticmethod
    def _committed_by_topic(
        group_metadata: ConsumerGroupDescription,
        snapshot: GroupSnapshot,
        topics: dict[str, Topic],
    ) -> dict[str, list[TopicPartition]]:
        committed_by_topic: dict[str, list[TopicPartition]] = {}
        for committed in snapshot.offsets_for(group_metadata.group_id):
            topic_name = str(committed.topic)
            if committed.offset == OFFSET_INVALID or topic_name not in topics:
                continue
            committed_by_topic.setdefault(topic_name, []).append(committed)
        return committed_by_topic

    def _map_group(
        self,
        metadata: ConsumerGroupDescription,
        topic_name: str,
        committed_partitions: list[TopicPartition],
        partitions: dict[tuple[str, int], Partition],
    ) -> Group:
        group = Group(
            id=metadata.group_id,
            partition_assignor=metadata.partition_assignor,
            state=str(getattr(metadata.state, "name", metadata.state)).lower(),
            coordinator=self._map_coordinator(metadata.coordinator),
        )
        group.partitions = self._map_group_partitions(
            metadata.group_id, topic_name, committed_partitions, partitions
        )
        group.members = self._map_group_members(metadata, topic_name)
        return group

    @staticmethod
    def _map_coordinator(coordinator: Any) -> Node | None:
        if coordinator is None:
            return None
        return Node(
            id=coordinator.id,
            host=coordinator.host,
            port=coordinator.port,
            rack=coordinator.rack,
        )

    @staticmethod
    def _map_group_partitions(
        group_id: str,
        topic_name: str,
        committed_partitions: list[TopicPartition],
        partitions: dict[tuple[str, int], Partition],
    ) -> list[GroupPartition]:
        return [
            GroupPartition(
                id=committed.partition,
                topic=topic_name,
                offset=committed.offset,
                group=group_id,
                high=partition.high,
                low=partition.low,
            )
            for committed in committed_partitions
            if (partition := partitions.get((topic_name, committed.partition))) is not None
        ]

    @staticmethod
    def _map_group_members(
        metadata: ConsumerGroupDescription, topic_name: str
    ) -> list[GroupMember]:
        members: list[GroupMember] = []
        for member in metadata.members:
            assignments = [
                assigned.partition
                for assigned in member.assignment.topic_partitions
                if assigned.topic == topic_name
            ]
            if assignments:
                members.append(
                    GroupMember(
                        id=member.member_id,
                        group=metadata.group_id,
                        client_id=member.client_id,
                        host=member.host,
                        instance_id=member.group_instance_id,
                        assignment=assignments,
                    )
                )
        return members

    def _map_topics(self, topics_metadata: list[TopicMetadata]) -> dict[str, Topic]:
        topics: dict[str, Topic] = {}
        for topic_metadata in topics_metadata:
            topic_name = str(topic_metadata.topic)
            topic = Topic(name=topic_name)
            topics[topic_name] = topic
            for partition_metadata in topic_metadata.partitions.values():
                topic.partitions.append(
                    Partition(
                        id=partition_metadata.id,
                        topic=topic_name,
                        leader=partition_metadata.leader,
                        replicas=partition_metadata.replicas,
                        isrs=partition_metadata.isrs,
                    )
                )
        return topics

    def _list_topics_metadata(self) -> list[TopicMetadata]:
        def sort_by_topic_name(topic: TopicMetadata) -> Any:
            return str(topic.topic).lower()

        return sorted(
            self.admin_client.list_topics(timeout=self.timeout).topics.values(),
            key=sort_by_topic_name,
        )
