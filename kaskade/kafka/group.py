from typing import List

from confluent_kafka.admin import AdminClient, GroupMetadata

from kaskade.config import Config


class GroupService:
    def __init__(self, config: Config):
        if not config.kafka:
            raise Exception("Config not found")
        self.config = config

    def groups(self) -> List[GroupMetadata]:
        admin_client = AdminClient(self.config.kafka)
        groups: List[GroupMetadata] = admin_client.list_groups()
        return groups

    def groups_by_topic(self, topic: str) -> List[GroupMetadata]:
        all_groups = self.groups()
        groups = set()
        for group in all_groups:
            for member in group.members:
                if topic.encode() in member.assignment:
                    groups.add(group)
                    break

        return list(groups)


if __name__ == "__main__":
    config = Config("kaskade.yml")
    group_service = GroupService(config)
    groups = group_service.groups()
    print(groups)
