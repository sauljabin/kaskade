import uuid
from datetime import datetime
from typing import Any

from confluent_kafka import Consumer, TopicPartition, OFFSET_INVALID, KafkaException
from confluent_kafka.admin import (
    AdminClient,
    TopicMetadata,
    DescribeClusterResult,
    ConsumerGroupDescription,
    PartitionMetadata,
    ConfigResource,
    ResourceType,
    ConfigEntry,
    AlterConfigOpType,
    ConfigSource,
)
from confluent_kafka.cimpl import NewTopic, NewPartitions

from kaskade import logger
from kaskade.configs import MILLISECONDS_24H
from kaskade.models import (
    Topic,
    Cluster,
    Node,
    Partition,
    Group,
    GroupPartition,
    GroupMember,
    Record,
    Header,
)
from kaskade.deserializers import Format, DeserializerPool
from kaskade.utils import make_it_async


class ConsumerService:
    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, str],
        deserializer_factory: DeserializerPool,
        key_format: Format,
        value_format: Format,
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
        self.key_format = key_format
        self.value_format = value_format
        self.stable = False
        self.consumer = Consumer(
            kafka_config
            | {
                "group.id": f"kaskade-{uuid.uuid4()}",
                "enable.auto.commit": False,
                "max.poll.interval.ms": MILLISECONDS_24H,
                "logger": logger,
            }
        )
        self.consumer.subscribe([topic], on_assign=self.on_assign)
        self.deserializer_factory = deserializer_factory

    def on_assign(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        self.stable = True

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
        records: list[Record] = []
        poll_retries = 0
        stabilization_retries = 0

        while len(records) < self.page_size:
            if poll_retries >= self.poll_retries:
                break

            if stabilization_retries >= self.stabilization_retries:
                break

            record_metadata = await make_it_async(self.consumer.poll, self.timeout)

            if not self.stable:
                stabilization_retries += 1
                continue
            stabilization_retries = 0

            if record_metadata is None:
                poll_retries += 1
                continue
            poll_retries = 0

            if record_metadata.error():
                raise KafkaException(record_metadata.error())

            timestamp_available, timestamp = record_metadata.timestamp()
            date = (
                datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
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
                            value_deserializer=self.deserializer_factory.get(Format.STRING),
                        )
                        for key, value in record_metadata.headers()
                    ]
                    if record_metadata.headers() is not None
                    else []
                ),
                key_format=self.key_format,
                value_format=self.value_format,
                key_deserializer=self.deserializer_factory.get(self.key_format),
                value_deserializer=self.deserializer_factory.get(self.value_format),
            )

            if partition_filter is not None:
                if record.partition != partition_filter:
                    continue

            if key_filter:
                if key_filter not in record.key_str():
                    continue

            if value_filter:
                if value_filter not in record.value_str():
                    continue

            if header_filter:
                if record.headers is None:
                    continue

                if not [header for header in record.headers if header_filter in header.value_str()]:
                    continue

            records.append(record)

        return records


class ClusterService:
    def __init__(self, config: dict[str, str], *, timeout: float = 2.0) -> None:
        self.timeout = timeout
        self.admin_client = AdminClient(config | {"logger": logger})

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


class TopicService:
    def __init__(self, config: dict[str, str], *, timeout: float = 2.0) -> None:
        self.timeout = timeout
        self.config = config.copy() | {"logger": logger}
        self.admin_client = AdminClient(self.config)

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
        topics = await self._map_topics(self._list_topics_metadata())
        await self._map_groups_into_topics(self._list_groups_metadata(), topics)
        return topics

    async def _map_groups_into_topics(
        self, groups_metadata: list[ConsumerGroupDescription], topics: dict[str, Topic]
    ) -> None:
        for group_metadata in groups_metadata:
            group_consumer = Consumer(self.config | {"group.id": group_metadata.group_id})
            for topic in topics.values():

                coordinator = Node(
                    id=group_metadata.coordinator.id,
                    host=group_metadata.coordinator.host,
                    port=group_metadata.coordinator.port,
                    rack=group_metadata.coordinator.rack,
                )

                group = Group(
                    id=group_metadata.group_id,
                    partition_assignor=group_metadata.partition_assignor,
                    state=str(group_metadata.state.name.lower()),
                    coordinator=coordinator,
                )

                topic_partitions_for_this_group_metadata = [
                    TopicPartition(topic.name, partition.id) for partition in topic.partitions
                ]

                committed_partitions_metadata = await make_it_async(
                    group_consumer.committed,
                    topic_partitions_for_this_group_metadata,
                    timeout=self.timeout,
                )

                for group_partition_metadata in committed_partitions_metadata:
                    if group_partition_metadata.offset == OFFSET_INVALID:
                        continue

                    low_group_partition_watermark, high_group_partition_watermark = 0, 0

                    try:
                        low_group_partition_watermark, high_group_partition_watermark = (
                            await make_it_async(
                                group_consumer.get_watermark_offsets,
                                group_partition_metadata,
                                timeout=self.timeout,
                                cached=False,
                            )
                        )
                    except KafkaException as ex:
                        logger.exception(ex)

                    group_partition = GroupPartition(
                        id=group_partition_metadata.partition,
                        topic=group_partition_metadata.topic,
                        offset=group_partition_metadata.offset,
                        group=group_metadata.group_id,
                        high=high_group_partition_watermark,
                        low=low_group_partition_watermark,
                    )

                    group.partitions.append(group_partition)

                if len(group.partitions) > 0:
                    for member_metadata in group_metadata.members:
                        member_partitions = [
                            topic_partition.partition
                            for topic_partition in member_metadata.assignment.topic_partitions
                            if topic.name == topic_partition.topic
                        ]
                        if len(member_partitions) > 0:
                            member = GroupMember(
                                id=member_metadata.member_id,
                                group=group_metadata.group_id,
                                client_id=member_metadata.client_id,
                                host=member_metadata.host,
                                instance_id=member_metadata.group_instance_id,
                                assignment=member_partitions,
                            )
                            group.members.append(member)

                    topic.groups.append(group)

    async def _map_topics(self, topics_metadata: list[TopicMetadata]) -> dict[str, Topic]:
        topics = {}

        for topic_metadata in topics_metadata:
            topic = Topic(name=topic_metadata.topic)
            topics[topic_metadata.topic] = topic

            for topic_partition_metadata in topic_metadata.partitions.values():
                low_topic_partition_watermark, high_topic_partition_watermark = (
                    await self._get_watermarks(topic_metadata, topic_partition_metadata)
                )

                partition = Partition(
                    id=topic_partition_metadata.id,
                    topic=topic_metadata.topic,
                    leader=topic_partition_metadata.leader,
                    replicas=topic_partition_metadata.replicas,
                    isrs=topic_partition_metadata.isrs,
                    high=high_topic_partition_watermark,
                    low=low_topic_partition_watermark,
                )

                topic.partitions.append(partition)

        return topics

    async def _get_watermarks(
        self, topic_metadata: TopicMetadata, partition_metadata: PartitionMetadata
    ) -> tuple[int, int]:
        low, high = 0, 0

        consumer = Consumer(self.config | {"group.id": f"kaskade-{uuid.uuid4()}"})

        try:
            low, high = await make_it_async(
                consumer.get_watermark_offsets,
                TopicPartition(topic_metadata.topic, partition_metadata.id),
                timeout=self.timeout,
                cached=False,
            )
        except KafkaException as ex:
            logger.exception(ex)

        return low, high

    def _list_groups_metadata(self) -> list[ConsumerGroupDescription]:
        group_names: list[str] = [
            group.group_id
            for group in self.admin_client.list_consumer_groups(request_timeout=self.timeout)
            .result()
            .valid
        ]

        if not group_names:
            return []

        return [
            future.result()
            for group_id, future in self.admin_client.describe_consumer_groups(
                group_names, request_timeout=self.timeout
            ).items()
        ]

    def _list_topics_metadata(self) -> list[TopicMetadata]:
        def sort_by_topic_name(topic: TopicMetadata) -> Any:
            return topic.topic.lower()

        return sorted(
            list(self.admin_client.list_topics(timeout=self.timeout).topics.values()),
            key=sort_by_topic_name,
        )
