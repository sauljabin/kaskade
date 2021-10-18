from operator import attrgetter
from typing import List

from confluent_kafka.admin import AdminClient, PartitionMetadata, TopicMetadata

from kaskade.config import Config
from kaskade.kafka import TIMEOUT
from kaskade.kafka.group_service import GroupService
from kaskade.kafka.models import Partition, Topic


class TopicService:
    def __init__(self, config: Config) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
        self.config = config

    def topics(self) -> List[Topic]:
        def metadata_to_partition(metadata: PartitionMetadata) -> Partition:
            return Partition(
                id=metadata.id,
                leader=metadata.leader,
                replicas=metadata.replicas,
                isrs=metadata.isrs,
            )

        def metadata_to_topic(metadata: TopicMetadata) -> Topic:
            name = metadata.topic
            partitions = list(metadata.partitions.values())

            group_service = GroupService(self.config)
            groups = group_service.groups_by_topic(name)

            return Topic(
                name=name,
                partitions=list(map(metadata_to_partition, partitions)),
                groups=groups,
            )

        admin_client = AdminClient(self.config.kafka)
        raw_topics = list(admin_client.list_topics(timeout=TIMEOUT).topics.values())
        topics = list(map(metadata_to_topic, raw_topics))
        return sorted(topics, key=attrgetter("name"))
