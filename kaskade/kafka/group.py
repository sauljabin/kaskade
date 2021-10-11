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


if __name__ == "__main__":

    config = Config("kaskade.yml")
    group_service = GroupService(config)
    groups = group_service.groups()
    for group in groups:
        print(group)
        for member in group.members:
            print("\t", member.metadata)
