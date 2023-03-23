import uuid
from operator import attrgetter
from typing import List

from confluent_kafka import OFFSET_INVALID, Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, ConsumerGroupDescription, TopicMetadata

from kaskade.config import Config
from kaskade.kafka import TIMEOUT
from kaskade.kafka.mappers import (
    metadata_to_group,
    metadata_to_group_member,
    metadata_to_group_partition,
    metadata_to_partition,
    metadata_to_topic,
)
from kaskade.kafka.models import Group, Topic


class TopicService:
    def __init__(self, config: Config) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
        self.config = config
        self.admin_client = AdminClient(self.config.kafka)
        config_copy = self.config.kafka.copy()
        config_copy["group.id"] = str(uuid.uuid4())
        self.consumer = Consumer(config_copy)

    def groups_by_topic(self, topic: TopicMetadata, group_names: List[str]) -> List[Group]:
        partitions = [TopicPartition(topic.topic, p) for p in topic.partitions]

        groups: List[Group] = []

        group_items = (
            self.admin_client.describe_consumer_groups(group_names, request_timeout=TIMEOUT).items()
            if group_names
            else []
        )

        for group_id, group_future_request in group_items:
            group_metadata: ConsumerGroupDescription = group_future_request.result()

            group: Group = metadata_to_group(group_metadata)

            config = self.config.kafka.copy()
            config["group.id"] = group.id

            consumer = Consumer(config)
            committed = consumer.committed(partitions, timeout=TIMEOUT)

            for partition in committed:
                if partition.offset == OFFSET_INVALID:
                    continue
                else:
                    low, high = consumer.get_watermark_offsets(
                        partition, timeout=TIMEOUT, cached=False
                    )
                    group_partition = metadata_to_group_partition(group.id, partition)
                    group_partition.low = low
                    group_partition.high = high

                    group.partitions.append(group_partition)

            if len(group.partitions) > 0:
                for member_metadata in group_metadata.members:
                    member = metadata_to_group_member(group.id, member_metadata)

                    for topic_partition in member_metadata.assignment.topic_partitions:
                        if topic.topic == topic_partition.topic:
                            group.members.append(member)
                            break
                groups.append(group)

        return sorted(groups, key=attrgetter("id"))

    def map_raw_topic(self, raw_topic: TopicMetadata, groups: List[str]) -> Topic:
        topic = metadata_to_topic(raw_topic)

        topic.groups = self.groups_by_topic(raw_topic, groups)

        topic.partitions = []
        for raw_partition in raw_topic.partitions.values():
            partition = metadata_to_partition(raw_partition)
            topic.partitions.append(partition)

            low, high = self.consumer.get_watermark_offsets(
                TopicPartition(topic.name, raw_partition.id),
                timeout=TIMEOUT,
                cached=False,
            )
            partition.low = low
            partition.high = high
        return topic

    def list(self) -> List[Topic]:
        raw_topics: List[TopicMetadata] = sorted(
            list(self.admin_client.list_topics(timeout=TIMEOUT).topics.values()),
            key=attrgetter("topic"),
        )

        topics: List[Topic] = []

        groups: List[str] = [
            group.group_id
            for group in self.admin_client.list_consumer_groups(request_timeout=TIMEOUT)
            .result()
            .valid
        ]

        for raw_topic in raw_topics:
            topics.append(self.map_raw_topic(raw_topic, groups))

        return topics


if __name__ == "__main__":
    config = Config("../../kaskade.yml")
    topic_service = TopicService(config)
    topic_list = topic_service.list()
    print(topic_list)
