from confluent_kafka.admin import AdminClient


class GroupService:
    def __init__(self, config):
        if not config or not config.kafka:
            raise Exception("Config not found")
        self.config = config

    def groups(self):
        admin_client = AdminClient(self.config.kafka)
        return admin_client.list_groups()


class Group:
    pass


if __name__ == "__main__":

    class Config:
        kafka = {"bootstrap.servers": "localhost:9093"}

    config = Config()
    group_service = GroupService(config)
    groups = group_service.groups()
    for group in groups:
        print(group)
        for member in group.members:
            print("\t", member.metadata)
