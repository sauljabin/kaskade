from operator import attrgetter
from typing import List, Optional

from confluent_kafka.admin import AdminClient

from kaskade.config import Config
from kaskade.kafka import TIMEOUT
from kaskade.kafka.group_service import GroupService
from kaskade.kafka.mappers import metadata_to_topic
from kaskade.kafka.models import Topic


class TopicService:
    def __init__(self, config: Config) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
        self.config = config

    def list(self) -> List[Topic]:
        admin_client = AdminClient(self.config.kafka)
        raw_topics = list(admin_client.list_topics(timeout=TIMEOUT).topics.values())

        def add_groups(topic: Topic) -> Topic:
            groups_service = GroupService(self.config)
            topic.groups = groups_service.find_by_topic_name(topic.name)
            return topic

        topics = list(map(add_groups, map(metadata_to_topic, raw_topics)))
        return sorted(topics, key=attrgetter("name"))

    def find_by_name(self, name: str) -> Optional[Topic]:
        topics = self.list()

        for topic in topics:
            if topic.name == name:
                return topic

        return None


if __name__ == "__main__":
    config = Config("../../kaskade.yml")
    topic_service = TopicService(config)
    print(topic_service.list())
    print(topic_service.find_by_name("kafka-cluster.test"))
