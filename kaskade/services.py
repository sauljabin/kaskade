import asyncio
import functools
import uuid
from datetime import datetime
from operator import attrgetter
from typing import List, Tuple

from confluent_kafka import Consumer, TopicPartition, OFFSET_INVALID, KafkaException
from confluent_kafka.admin import (
    AdminClient,
    TopicMetadata,
    DescribeClusterResult,
    ConsumerGroupDescription,
    PartitionMetadata,
)

from kaskade.models import (
    Topic,
    Cluster,
    Node,
    Partition,
    Group,
    GroupPartition,
    GroupMember,
    Record,
)


class ConsumerService:
    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, str],
        *,
        page_size: int = 30,
        max_retries: int = 5,
        timeout: float = 1.0,
    ) -> None:
        self.topic = topic
        self.page_size = page_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.consumer = Consumer(
            kafka_config | {"group.id": f"kaskade-{uuid.uuid4()}", "enable.auto.commit": False}
        )
        self.consumer.subscribe([topic])
        self.loop = asyncio.get_running_loop()
        self.poll = functools.partial(self.consumer.poll, self.timeout)

    def close(self) -> None:
        self.consumer.unsubscribe()
        self.consumer.close()

    async def consume(self) -> List[Record]:
        records: List[Record] = []
        retries = 0

        while len(records) < self.page_size:
            if retries >= self.max_retries:
                break

            record_metadata = await self.loop.run_in_executor(None, self.poll)

            if record_metadata is None:
                retries += 1
                continue

            if record_metadata.error():
                raise KafkaException(record_metadata.error())

            retries = 0

            timestamp_available, timestamp = record_metadata.timestamp()
            date = datetime.fromtimestamp(timestamp / 1000) if timestamp_available > 0 else None

            record = Record(
                partition=record_metadata.partition(),
                offset=record_metadata.offset(),
                key=record_metadata.key(),
                value=record_metadata.value(),
                date=date,
                headers=record_metadata.headers(),
            )
            records.append(record)

        return records


class ClusterService:
    def __init__(self, config: dict[str, str], *, timeout: float = 2.0) -> None:
        self.timeout = timeout
        self.admin_client = AdminClient(config)

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
        self.config = config.copy()
        self.admin_client = AdminClient(self.config)
        self.consumer = Consumer(self.config | {"group.id": f"kaskade-{uuid.uuid4()}"})

    def all(self) -> List[Topic]:
        topics = self._map_topics(self._list_topics_metadata())
        self._map_groups_into_topics(self._list_groups_metadata(), topics)
        return topics

    def _map_groups_into_topics(
        self, groups_metadata: List[ConsumerGroupDescription], topics: List[Topic]
    ) -> None:
        for group_metadata in groups_metadata:
            group_consumer = Consumer(self.config | {"group.id": group_metadata.group_id})
            for topic in topics:

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

                committed_partitions_metadata = group_consumer.committed(
                    topic_partitions_for_this_group_metadata, timeout=self.timeout
                )

                for group_partition_metadata in committed_partitions_metadata:
                    if group_partition_metadata.offset == OFFSET_INVALID:
                        continue

                    low_group_partition_watermark, high_group_partition_watermark = (
                        group_consumer.get_watermark_offsets(
                            group_partition_metadata, timeout=self.timeout, cached=False
                        )
                    )

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

    def _map_topics(self, topics_metadata: List[TopicMetadata]) -> List[Topic]:
        topics = []
        for topic_metadata in topics_metadata:
            topic = Topic(name=topic_metadata.topic)
            topics.append(topic)

            for topic_partition_metadata in topic_metadata.partitions.values():
                low_topic_partition_watermark, high_topic_partition_watermark = (
                    self._get_watermarks(topic_metadata, topic_partition_metadata)
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

    def _get_watermarks(
        self, topic_metadata: TopicMetadata, partition_metadata: PartitionMetadata
    ) -> Tuple[int, int]:
        low, high = self.consumer.get_watermark_offsets(
            TopicPartition(topic_metadata.topic, partition_metadata.id),
            timeout=self.timeout,
            cached=False,
        )
        return low, high

    def _list_groups_metadata(self) -> List[ConsumerGroupDescription]:
        group_names: List[str] = [
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

    def _list_topics_metadata(self) -> List[TopicMetadata]:
        return sorted(
            list(self.admin_client.list_topics(timeout=self.timeout).topics.values()),
            key=attrgetter("topic"),
        )
