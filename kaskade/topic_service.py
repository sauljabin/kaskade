import asyncio
from collections.abc import Mapping
from concurrent.futures import Future
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, cast

from confluent_kafka import (
    OFFSET_INVALID,
    ConsumerGroupTopicPartitions,
    KafkaError,
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
from kaskade.commands import CreateTopicCommand
from kaskade.concurrency import run_blocking
from kaskade.configs import (
    CLEANUP_POLICY_CONFIG,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
)
from kaskade.models import (
    Group,
    GroupMember,
    GroupPartition,
    MetricState,
    Node,
    Partition,
    Topic,
    TopicConfiguration,
)
from kaskade.timeouts import TimeoutConfig

# Expected admin request failures. confluent-kafka raises ValueError for requests it rejects
# before sending them; any other exception is a programming error and must propagate.
ADMIN_EXCEPTIONS: tuple[type[Exception], ...] = (KafkaException, ValueError)


def _wait_for(futures: Mapping[Any, Future[Any]]) -> None:
    """Wait for every admin request future, raising the first failure."""
    for future in futures.values():
        future.result()


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

    def __init__(
        self,
        config: dict[str, Any],
        *,
        timeouts: TimeoutConfig | None = None,
    ) -> None:
        self.timeouts = timeouts or TimeoutConfig()
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
        futures = self.admin_client.create_topics(
            [new_topic], request_timeout=self.timeouts.admin_write
        )
        _wait_for(futures)

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
        futures = self.admin_client.describe_configs(
            [resource], request_timeout=self.timeouts.admin_read
        )
        configs = next(iter(futures.values())).result()
        return list(configs.values())

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

        futures = self.admin_client.incremental_alter_configs(
            [resource], request_timeout=self.timeouts.admin_write
        )
        _wait_for(futures)

    def add_partitions(self, name: str, partitions: int) -> None:
        futures = self.admin_client.create_partitions(
            [NewPartitions(name, partitions)],
            request_timeout=self.timeouts.admin_write,
            validate_only=False,
        )
        _wait_for(futures)

    def delete(self, name: str) -> None:
        futures = self.admin_client.delete_topics([name], request_timeout=self.timeouts.admin_write)
        _wait_for(futures)

    async def metadata(self) -> dict[str, Topic]:
        started_at = perf_counter()
        topics_metadata = await run_blocking(self._list_topics_metadata)
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
                request_timeout=self.timeouts.admin_read,
            )
            latest_futures = self.admin_client.list_offsets(
                {
                    topic_partition: OffsetSpec.latest()  # type: ignore[no-untyped-call]
                    for topic_partition in partitions
                },
                request_timeout=self.timeouts.admin_read,
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

        descriptions, description_failures = await self._load_group_descriptions(group_ids)
        offsets, offset_failures = await self._load_group_offsets(group_ids)
        hidden = self._unauthorized_group_ids(description_failures, offset_failures)
        errors = (
            *list_errors,
            *self._group_errors("description", description_failures),
            *self._group_errors("offsets", offset_failures),
        )
        if hidden:
            logger.info("admin groups hidden (not authorized)=%d", len(hidden))
        logger.info(
            "admin groups loaded groups=%d errors=%d elapsed=%.3fs",
            len(group_ids) - len(hidden),
            len(errors),
            perf_counter() - started_at,
        )
        return GroupSnapshot(
            tuple(item for item in descriptions if item.group_id not in hidden),
            {group_id: item for group_id, item in offsets.items() if group_id not in hidden},
            errors,
        )

    @staticmethod
    def _is_group_authorization_error(error: Exception) -> bool:
        kafka_error = error.args[0] if isinstance(error, KafkaException) and error.args else None
        return (
            isinstance(kafka_error, KafkaError)
            and kafka_error.code() == KafkaError.GROUP_AUTHORIZATION_FAILED
        )

    def _unauthorized_group_ids(self, *failures: dict[str, Exception]) -> set[str]:
        # Cluster Describe lists every group, but the principal may not describe them all.
        # Those groups belong to other applications; they are hidden, not failed.
        return {
            group_id
            for stage_failures in failures
            for group_id, error in stage_failures.items()
            if self._is_group_authorization_error(error)
        }

    def _group_errors(self, stage: str, failures: dict[str, Exception]) -> tuple[Exception, ...]:
        errors: list[Exception] = []
        for group_id, error in failures.items():
            if not self._is_group_authorization_error(error):
                logger.error("admin consumer-group %s failed for %s: %s", stage, group_id, error)
                errors.append(error)
        return tuple(errors)

    async def _list_group_ids(self) -> tuple[tuple[str, ...], tuple[Exception, ...]]:
        try:
            list_result = await asyncio.wrap_future(
                self.admin_client.list_consumer_groups(request_timeout=self.timeouts.admin_read)
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
    ) -> tuple[tuple[ConsumerGroupDescription, ...], dict[str, Exception]]:
        description_futures = self.admin_client.describe_consumer_groups(
            list(group_ids), request_timeout=self.timeouts.admin_read
        )
        description_results = await asyncio.gather(
            *(self._resolve_future(future) for future in description_futures.values())
        )
        descriptions: list[ConsumerGroupDescription] = []
        failures: dict[str, Exception] = {}
        for group_id, (description, error) in zip(
            description_futures, description_results, strict=True
        ):
            if error is not None:
                failures[group_id] = error
            elif description is not None:
                descriptions.append(description)
        return tuple(descriptions), failures

    async def _load_group_offsets(
        self, group_ids: tuple[str, ...]
    ) -> tuple[dict[str, tuple[TopicPartition, ...]], dict[str, Exception]]:
        semaphore = asyncio.Semaphore(self.GROUP_OFFSET_CONCURRENCY)
        offset_results = await asyncio.gather(
            *(self._load_single_group_offsets(group_id, semaphore) for group_id in group_ids)
        )
        offsets: dict[str, tuple[TopicPartition, ...]] = {}
        failures: dict[str, Exception] = {}
        for group_id, topic_partitions, error in offset_results:
            if error is not None:
                failures[group_id] = error
            else:
                offsets[group_id] = topic_partitions
        return offsets, failures

    async def _load_single_group_offsets(
        self, group_id: str, semaphore: asyncio.Semaphore
    ) -> tuple[str, tuple[TopicPartition, ...], Exception | None]:
        async with semaphore:
            try:
                futures = self.admin_client.list_consumer_group_offsets(
                    [ConsumerGroupTopicPartitions(group_id)],
                    request_timeout=self.timeouts.admin_read,
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

    @staticmethod
    async def _resolve_future(future: Any) -> tuple[Any | None, Exception | None]:
        try:
            return await asyncio.wrap_future(future), None
        except ADMIN_EXCEPTIONS as ex:
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
            self.admin_client.list_topics(timeout=self.timeouts.admin_read).topics.values(),
            key=sort_by_topic_name,
        )
