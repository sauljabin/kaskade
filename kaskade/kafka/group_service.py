from typing import List

from confluent_kafka.admin import AdminClient

from kaskade.config import Config
from kaskade.kafka.mappers import metadata_to_group
from kaskade.kafka.models import Group


class GroupService:
    def __init__(self, config: Config):
        if not config.kafka:
            raise Exception("Config not found")
        self.config = config

    def groups(self) -> List[Group]:
        admin_client = AdminClient(self.config.kafka)
        groups = admin_client.list_groups()
        return list(map(metadata_to_group, groups))

    def groups_by_topic(self, topic: str) -> List[Group]:
        admin_client = AdminClient(self.config.kafka)
        all_groups = admin_client.list_groups()

        groups = set()
        for group in all_groups:
            for member in group.members:
                if topic.encode() in member.assignment:
                    groups.add(group)
                    break

        return list(map(metadata_to_group, groups))
