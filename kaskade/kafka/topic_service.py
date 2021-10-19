from operator import attrgetter
from typing import List

from confluent_kafka.admin import AdminClient

from kaskade.config import Config
from kaskade.kafka import TIMEOUT
from kaskade.kafka.mappers import metadata_to_group, metadata_to_topic
from kaskade.kafka.models import Topic


class TopicService:
    def __init__(self, config: Config) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
        self.config = config

    def topics(self) -> List[Topic]:
        admin_client = AdminClient(self.config.kafka)
        all_groups = admin_client.list_groups()
        raw_topics = list(admin_client.list_topics(timeout=TIMEOUT).topics.values())

        def add_groups(topic: Topic) -> Topic:
            groups = set()
            for group in all_groups:
                for member in group.members:
                    if topic.name.encode() in member.assignment:
                        groups.add(group)
                        break

            topic.groups = list(map(metadata_to_group, groups))
            return topic

        topics = list(map(add_groups, map(metadata_to_topic, raw_topics)))
        return sorted(topics, key=attrgetter("name"))
