from confluent_kafka.admin import AdminClient

from kaskade.kafka import TIMEOUT


class Topic:
    def __init__(self, name=None, partitions=None):
        self.name = name
        self.partitions = partitions

    def __str__(self):
        return self.name


class TopicService:
    def __init__(self, config):
        if not config or not config.kafka:
            raise Exception("Config not found")
        self.config = config

    def topics(self):
        def metadata_to_topic(metadata):
            name = metadata.topic
            partitions = list(metadata.partitions.values())
            return Topic(name=name, partitions=partitions)

        admin_client = AdminClient(self.config.kafka)
        raw_topics = list(admin_client.list_topics(timeout=TIMEOUT).topics.values())
        topics = list(map(metadata_to_topic, raw_topics))
        topics.sort(key=lambda topic: topic.name)
        return topics


if __name__ == "__main__":

    class Config:
        kafka = {"bootstrap.servers": "localhost:9093"}
        schema_registry = {}

    config = Config()
    topic_service = TopicService(config)
    topics = topic_service.topics()
    print([str(topic) for topic in topics])
