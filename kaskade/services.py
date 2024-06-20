import uuid
from operator import attrgetter
from typing import List, Tuple

from confluent_kafka import Consumer, TopicPartition, OFFSET_INVALID
from confluent_kafka.admin import (
    AdminClient,
    TopicMetadata,
    DescribeClusterResult,
    ConsumerGroupDescription,
    PartitionMetadata,
)

from kaskade.models import Topic, Cluster, Node, Partition, Group, GroupPartition, GroupMember

DEFAULT_TIMEOUT = 2.0


class ClusterService:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config.copy()
        self.admin_client = AdminClient(self.config)

    def get(self) -> Cluster:
        cluster_metadata: DescribeClusterResult = self.admin_client.describe_cluster(
            request_timeout=DEFAULT_TIMEOUT
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
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config.copy()
        self.admin_client = AdminClient(self.config)
        self.consumer = Consumer(self.config | {"group.id": uuid.uuid4()})

    def list(self) -> List[Topic]:
        topics_metadata = self._list_topics_metadata()
        groups_metadata = self._list_groups_metadata()

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

            for group_metadata in groups_metadata:
                group_consumer = Consumer(self.config | {"group.id": group_metadata.group_id})

                topic_partitions_for_this_group_metadata = [
                    TopicPartition(topic_metadata.topic, partition)
                    for partition in topic_metadata.partitions
                ]

                committed_partitions_metadata = group_consumer.committed(
                    topic_partitions_for_this_group_metadata, timeout=DEFAULT_TIMEOUT
                )

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

                for group_partition_metadata in committed_partitions_metadata:
                    if group_partition_metadata.offset == OFFSET_INVALID:
                        continue

                    low_group_partition_watermark, high_group_partition_watermark = (
                        group_consumer.get_watermark_offsets(
                            group_partition_metadata, timeout=DEFAULT_TIMEOUT, cached=False
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
                        for topic_partition in member_metadata.assignment.topic_partitions:
                            if topic_metadata.topic == topic_partition.topic:
                                member = GroupMember(
                                    id=member_metadata.member_id,
                                    group=group_metadata.group_id,
                                    client_id=member_metadata.client_id,
                                    host=member_metadata.host,
                                    instance_id=member_metadata.group_instance_id,
                                )
                                group.members.append(member)
                                break
                    topic.groups.append(group)

        return topics

    def _get_watermarks(
        self, topic_metadata: TopicMetadata, partition_metadata: PartitionMetadata
    ) -> Tuple[int, int]:
        low, high = self.consumer.get_watermark_offsets(TopicPartition(topic_metadata.topic, partition_metadata.id),
                                                      timeout=DEFAULT_TIMEOUT, cached=False, )
        return low, high

    def _list_groups_metadata(self) -> List[ConsumerGroupDescription]:
        group_names: List[str] = [
            group.group_id
            for group in self.admin_client.list_consumer_groups(request_timeout=DEFAULT_TIMEOUT)
            .result()
            .valid
        ]

        if not group_names:
            return []

        return [
            future.result()
            for group_id, future in self.admin_client.describe_consumer_groups(
                group_names, request_timeout=DEFAULT_TIMEOUT
            ).items()
        ]

    def _list_topics_metadata(self) -> List[TopicMetadata]:
        return sorted(
            list(self.admin_client.list_topics(timeout=DEFAULT_TIMEOUT).topics.values()),
            key=attrgetter("topic"),
        )
