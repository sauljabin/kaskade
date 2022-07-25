import uuid
from operator import attrgetter
from typing import List

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, TopicMetadata

from kaskade.config import Config
from kaskade.kafka import TIMEOUT
from kaskade.kafka.group_service import GroupService
from kaskade.kafka.mappers import metadata_to_partition, metadata_to_topic
from kaskade.kafka.models import Topic


class TopicService:
    def __init__(self, config: Config) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
        self.config = config

    def list(self) -> List[Topic]:
        config = self.config.kafka.copy()
        config["group.id"] = str(uuid.uuid4())
        consumer = Consumer(config)

        admin_client = AdminClient(self.config.kafka)
        groups_service = GroupService(self.config)

        raw_topics: List[TopicMetadata] = list(
            admin_client.list_topics(timeout=TIMEOUT).topics.values()
        )
        topics = []

        for raw_topic in raw_topics:
            if not bool(self.config.kaskade.get("show.internals")):
                if raw_topic.topic.strip().startswith("_"):
                    continue

            topic = metadata_to_topic(raw_topic)
            topics.append(topic)

            topic.groups = groups_service.find_by_topic_name(topic.name)

            topic.partitions = []
            for raw_partition in raw_topic.partitions.values():
                partition = metadata_to_partition(raw_partition)
                topic.partitions.append(partition)

                low, high = consumer.get_watermark_offsets(
                    TopicPartition(topic.name, raw_partition.id),
                    timeout=TIMEOUT,
                    cached=False,
                )
                partition.low = low
                partition.high = high

        return sorted(topics, key=attrgetter("name"))


if __name__ == "__main__":
    config = Config("../../kaskade.yml")
    topic_service = TopicService(config)
    topic_list = topic_service.list()
    print(topic_list)
