from operator import attrgetter
from typing import List

from confluent_kafka import OFFSET_INVALID, Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, GroupMetadata, TopicMetadata

from kaskade.config import Config
from kaskade.kafka import TIMEOUT
from kaskade.kafka.mappers import (
    metadata_to_group,
    metadata_to_group_member,
    metadata_to_group_partition,
)
from kaskade.kafka.models import Group


class GroupService:
    def __init__(self, config: Config):
        if not config.kafka:
            raise Exception("Config not found")
        self.config = config

    def find_by_topic_name(self, topic_name: str) -> List[Group]:
        admin_client = AdminClient(self.config.kafka)
        all_topics: List[TopicMetadata] = list(
            admin_client.list_topics(timeout=TIMEOUT).topics.values()
        )
        filtered_topics = [
            metadata for metadata in all_topics if metadata.topic == topic_name
        ]

        if len(filtered_topics) > 0:
            topic = filtered_topics[0]
        else:
            return []

        partitions = [TopicPartition(topic.topic, p) for p in topic.partitions]

        all_groups: List[GroupMetadata] = admin_client.list_groups()
        groups: List[Group] = []

        for group_metadata in all_groups:
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
                    group_partition = metadata_to_group_partition(partition)
                    group_partition.group = group.id
                    group_partition.low = low
                    group_partition.high = high

                    group.partitions.append(group_partition)

            if len(group.partitions) > 0:
                for member_metadata in group_metadata.members:
                    member = metadata_to_group_member(member_metadata)
                    member.group = group.id
                    if topic_name.encode() in member_metadata.assignment:
                        group.members.append(member)
                groups.append(group)

        return sorted(groups, key=attrgetter("id"))


if __name__ == "__main__":
    config_main = Config("../../kaskade.yml")
    group_service = GroupService(config_main)
    groups_result = group_service.find_by_topic_name("kafka-cluster.test")
    print(groups_result)
