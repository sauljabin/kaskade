from operator import attrgetter
from typing import List

from confluent_kafka.admin import AdminClient, PartitionMetadata, TopicMetadata

from kaskade.config import Config
from kaskade.kafka import TIMEOUT


class Topic:
    def __init__(
        self,
        name: str = "",
        partitions: List[PartitionMetadata] = [],
    ) -> None:
        self.name = name
        self.partitions = partitions

    def __str__(self) -> str:
        return self.name


class TopicService:
    def __init__(self, config: Config) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
        self.config = config

    def topics(self) -> List[Topic]:
        def metadata_to_topic(metadata: TopicMetadata) -> Topic:
            name = metadata.topic
            partitions = list(metadata.partitions.values())
            return Topic(name=name, partitions=partitions)

        admin_client = AdminClient(self.config.kafka)
        raw_topics = list(admin_client.list_topics(timeout=TIMEOUT).topics.values())
        topics = list(map(metadata_to_topic, raw_topics))
        return sorted(topics, key=attrgetter("name"))


if __name__ == "__main__":
    config = Config("kaskade.yml")
    topic_service = TopicService(config)
    topics = topic_service.topics()
    print([str(topic) for topic in topics])
