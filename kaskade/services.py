import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from confluent_kafka import (
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
    DescribeClusterResult,
    OffsetSpec,
    ResourceType,
    TopicMetadata,
)
from confluent_kafka.cimpl import NewPartitions, NewTopic

from kaskade import logger
from kaskade.configs import ENABLE_AUTO_COMMIT, GROUP_ID, MAX_POLL_INTERVAL_MS, MILLISECONDS_24H
from kaskade.deserializers import Deserialization, DeserializerPool
from kaskade.models import (
    Cluster,
    Group,
    GroupMember,
    GroupPartition,
    Header,
    MetricState,
    Node,
    Partition,
    Record,
    Topic,
)
from kaskade.utils import make_it_async

ADMIN_EXCEPTIONS: tuple[type[Exception], ...] = (
    KafkaException,
    RuntimeError,
    TypeError,
    ValueError,
)


class ConsumerService:
    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, str],
        deserializer_factory: DeserializerPool,
        key_deserialization: Deserialization,
        value_deserialization: Deserialization,
        *,
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
        self.consumer.subscribe([topic], on_assign=self.on_assign)
        self.deserializer_factory = deserializer_factory

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
        self.consumer.unsubscribe()
        self.consumer.close()

    async def consume(
        self,
        *,
        partition_filter: int | None = None,
        key_filter: str | None = None,
        value_filter: str | None = None,
        header_filter: str | None = None,
    ) -> list[Record]:
        chunk_started_at = perf_counter()
        records: list[Record] = []
        poll_retries = 0
        stabilization_retries = 0
        scanned_records = 0
        first_record_at: float | None = None

        while len(records) < self.page_size:
            if poll_retries >= self.poll_retries:
                break

            if stabilization_retries >= self.stabilization_retries:
                break

            record_batch = await make_it_async(
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
                if record_metadata.error():
                    raise KafkaException(record_metadata.error())

                scanned_records += 1
                if first_record_at is None:
                    first_record_at = perf_counter()

                timestamp_available, timestamp = record_metadata.timestamp()
                date = (
                    datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    if timestamp_available > 0
                    else ""
                )

                record = Record(
                    topic=self.topic,
                    partition=record_metadata.partition(),
                    offset=record_metadata.offset(),
                    key=record_metadata.key(),
                    value=record_metadata.value(),
                    date=date,
                    headers=(
                        [
                            Header(
                                key=key,
                                value=value,
                                value_deserializer=self.deserializer_factory.get(
                                    Deserialization.STRING
                                ),
                            )
                            for key, value in record_metadata.headers()
                        ]
                        if record_metadata.headers() is not None
                        else []
                    ),
                    key_deserialization=self.key_deserialization,
                    value_deserialization=self.value_deserialization,
                    key_deserializer=self.deserializer_factory.get(self.key_deserialization),
                    value_deserializer=self.deserializer_factory.get(self.value_deserialization),
                )

                if partition_filter is not None and record.partition != partition_filter:
                    continue

                if key_filter and key_filter not in record.key_str():
                    continue

                if value_filter and value_filter not in record.value_str():
                    continue

                if header_filter:
                    if record.headers is None:
                        continue

                    if not [
                        header for header in record.headers if header_filter in header.value_str()
                    ]:
                        continue

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


class ClusterService:
    def __init__(
        self, config: dict[str, str | int | float | bool], *, timeout: float = 2.0
    ) -> None:
        self.timeout = timeout
        self.admin_client = AdminClient(config, logger=logger)

    def get(self) -> Cluster:
        cluster_metadata: DescribeClusterResult = self.admin_client.describe_cluster(
            request_timeout=self.timeout
        ).result()

        controller = Node(
            id=cluster_metadata.controller.id,
            host=cluster_metadata.controller.host,
            port=cluster_metadata.controller.port,
            rack=cluster_metadata.controller.rack,
        )

        nodes = [
            Node(
                id=node_metadata.id,
                host=node_metadata.host,
                port=node_metadata.port,
                rack=node_metadata.rack,
            )
            for node_metadata in cluster_metadata.nodes
        ]

        return Cluster(
            id=cluster_metadata.cluster_id,
            controller=controller,
            nodes=nodes,
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
    offsets: dict[str, tuple[TopicPartition, ...]] | None = None
    errors: tuple[Exception, ...] = ()

    def offsets_for(self, group_id: str) -> tuple[TopicPartition, ...]:
        return (self.offsets or {}).get(group_id, ())


class TopicService:
    GROUP_OFFSET_CONCURRENCY = 16

    def __init__(
        self, config: dict[str, str | int | float | bool], *, timeout: float = 2.0
    ) -> None:
        self.timeout = timeout
        self.config = config.copy()
        self.admin_client = AdminClient(self.config, logger=logger)

    def create(self, new_topics: list[NewTopic]) -> None:
        futures = self.admin_client.create_topics(new_topics)
        for future in futures.values():
            future.result()

    def get_configs(self, name: str) -> dict[str, str]:
        resource = ConfigResource(ResourceType.TOPIC, name)
        futures = self.admin_client.describe_configs([resource])
        for future in futures.values():
            configs = future.result()
            return {config.name: config.value for config in configs.values()}
        return {}

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

    async def all(self) -> dict[str, Topic]:
        topics = await self.metadata()
        offsets_task = asyncio.create_task(self.enrich_offsets(topics))
        groups_task = asyncio.create_task(self.load_groups())
        await offsets_task
        self.apply_groups(topics, await groups_task)
        return topics

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
        partitions = {
            TopicPartition(topic.name, partition.id): partition
            for topic in topics.values()
            for partition in topic.partitions
        }
        if not partitions:
            for topic in topics.values():
                topic.records_state = MetricState.READY
            return EnrichmentResult()

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
            for topic in topics.values():
                if topic.records_state is not MetricState.READY:
                    topic.records_state = MetricState.UNAVAILABLE
            return EnrichmentResult((ex,))

        earliest_task = asyncio.create_task(self._resolve_offset_futures(earliest_futures))
        latest_task = asyncio.create_task(self._resolve_offset_futures(latest_futures))
        earliest, earliest_errors = await earliest_task
        latest, latest_errors = await latest_task
        errors = (*earliest_errors, *latest_errors)

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

        logger.info(
            "admin offsets loaded partitions=%d errors=%d elapsed=%.3fs",
            len(partitions),
            len(errors),
            perf_counter() - started_at,
        )
        return EnrichmentResult(errors)

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
        errors: list[Exception] = []
        try:
            list_result = await asyncio.wrap_future(
                self.admin_client.list_consumer_groups(request_timeout=self.timeout)
            )
        except ADMIN_EXCEPTIONS as ex:
            logger.error("admin consumer-group listing failed: %s", ex)
            return GroupSnapshot(errors=(ex,))

        errors.extend(list_result.errors or [])
        group_ids = [group.group_id for group in list_result.valid or []]
        if not group_ids:
            return GroupSnapshot(errors=tuple(errors))

        descriptions: list[ConsumerGroupDescription] = []
        description_futures = self.admin_client.describe_consumer_groups(
            group_ids, request_timeout=self.timeout
        )
        description_results = await asyncio.gather(
            *(self._resolve_future(future) for future in description_futures.values())
        )
        for description, error in description_results:
            if error is not None:
                errors.append(error)
            elif description is not None:
                descriptions.append(description)

        semaphore = asyncio.Semaphore(self.GROUP_OFFSET_CONCURRENCY)

        async def load_offsets(
            group_id: str,
        ) -> tuple[str, tuple[TopicPartition, ...], Exception | None]:
            async with semaphore:
                try:
                    futures = self.admin_client.list_consumer_group_offsets(
                        [ConsumerGroupTopicPartitions(group_id)],
                        request_timeout=self.timeout,
                    )
                    result = await asyncio.wrap_future(futures[group_id])
                    topic_partitions = tuple(result.topic_partitions or ())
                    partition_errors = [
                        KafkaException(partition.error)
                        for partition in topic_partitions
                        if partition.error is not None
                    ]
                    if partition_errors:
                        return group_id, (), partition_errors[0]
                    return group_id, topic_partitions, None
                except ADMIN_EXCEPTIONS as ex:
                    return group_id, (), ex

        offset_results = await asyncio.gather(*(load_offsets(group_id) for group_id in group_ids))
        offsets: dict[str, tuple[TopicPartition, ...]] = {}
        for group_id, topic_partitions, error in offset_results:
            if error is not None:
                logger.error("admin consumer-group offsets failed for %s: %s", group_id, error)
                errors.append(error)
            else:
                offsets[group_id] = topic_partitions

        logger.info(
            "admin groups loaded groups=%d errors=%d elapsed=%.3fs",
            len(group_ids),
            len(errors),
            perf_counter() - started_at,
        )
        return GroupSnapshot(tuple(descriptions), offsets, tuple(errors))

    async def _resolve_future(self, future: Any) -> tuple[Any | None, Exception | None]:
        try:
            return await asyncio.wrap_future(future), None
        except ADMIN_EXCEPTIONS as ex:
            logger.error("admin request failed: %s", ex)
            return None, ex

    def apply_groups(self, topics: dict[str, Topic], snapshot: GroupSnapshot) -> EnrichmentResult:
        if snapshot.errors:
            for topic in topics.values():
                if topic.groups_state is not MetricState.READY:
                    topic.groups_state = MetricState.UNAVAILABLE
            return EnrichmentResult(snapshot.errors)

        for topic in topics.values():
            topic.groups = []
            topic.groups_state = (
                MetricState.READY
                if topic.records_state is MetricState.READY
                else MetricState.UNAVAILABLE
            )

        partitions = {
            (topic.name, partition.id): partition
            for topic in topics.values()
            for partition in topic.partitions
        }

        for group_metadata in snapshot.descriptions:
            committed_by_topic: dict[str, list[TopicPartition]] = {}
            for committed in snapshot.offsets_for(group_metadata.group_id):
                if committed.offset == OFFSET_INVALID or committed.topic not in topics:
                    continue
                committed_by_topic.setdefault(str(committed.topic), []).append(committed)

            for topic_name, committed_partitions in committed_by_topic.items():
                topic = topics[topic_name]
                coordinator = group_metadata.coordinator
                group = Group(
                    id=group_metadata.group_id,
                    partition_assignor=group_metadata.partition_assignor,
                    state=str(getattr(group_metadata.state, "name", group_metadata.state)).lower(),
                    coordinator=(
                        Node(
                            id=coordinator.id,
                            host=coordinator.host,
                            port=coordinator.port,
                            rack=coordinator.rack,
                        )
                        if coordinator is not None
                        else None
                    ),
                )

                for committed in committed_partitions:
                    partition = partitions.get((topic_name, committed.partition))
                    if partition is None:
                        continue
                    group.partitions.append(
                        GroupPartition(
                            id=committed.partition,
                            topic=topic_name,
                            offset=committed.offset,
                            group=group_metadata.group_id,
                            high=partition.high,
                            low=partition.low,
                        )
                    )

                if not group.partitions:
                    continue

                for member_metadata in group_metadata.members:
                    member_partitions = [
                        assigned.partition
                        for assigned in member_metadata.assignment.topic_partitions
                        if assigned.topic == topic_name
                    ]
                    if member_partitions:
                        group.members.append(
                            GroupMember(
                                id=member_metadata.member_id,
                                group=group_metadata.group_id,
                                client_id=member_metadata.client_id,
                                host=member_metadata.host,
                                instance_id=member_metadata.group_instance_id,
                                assignment=member_partitions,
                            )
                        )

                topic.groups.append(group)

        return EnrichmentResult()

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
