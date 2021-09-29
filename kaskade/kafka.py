from confluent_kafka.admin import AdminClient


class Kafka:
    def __init__(self, config):
        self.config = config

    def topics(self):
        admin_client = AdminClient(self.config)
        return admin_client.list_topics(timeout=2).topics
