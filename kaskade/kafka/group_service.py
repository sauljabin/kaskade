from typing import List

from confluent_kafka.admin import AdminClient, BrokerMetadata, GroupMetadata

from kaskade.config import Config
from kaskade.kafka.models import Broker, Group


class GroupService:
    def __init__(self, config: Config):
        if not config.kafka:
            raise Exception("Config not found")
        self.config = config

    def groups_by_topic(self, topic: str) -> List[Group]:
        admin_client = AdminClient(self.config.kafka)
        all_groups = admin_client.list_groups()

        groups = set()
        for group in all_groups:
            for member in group.members:
                if topic.encode() in member.assignment:
                    groups.add(group)
                    break

        def metadata_to_broker(metadata: BrokerMetadata) -> Broker:
            return Broker(id=metadata.id, host=metadata.host, port=metadata.port)

        def metadata_to_group(metadata: GroupMetadata) -> Group:
            return Group(
                id=metadata.id,
                broker=metadata_to_broker(metadata.broker),
                state=metadata.state,
                members=len(metadata.members),
            )

        return list(map(metadata_to_group, groups))
