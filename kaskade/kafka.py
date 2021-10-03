import concurrent

import confluent_kafka
from confluent_kafka.admin import AdminClient, ConfigResource

TIMEOUT = 0.5

# TODO service layer


class Kafka:
    def __init__(self, config):
        self.config = config

    def topics(self):
        topics_list = []

        if not self.config:
            return topics_list

        if not self.config.kafka:
            return topics_list

        admin_client = AdminClient(self.config.kafka)
        raw_topics = list(admin_client.list_topics(timeout=TIMEOUT).topics.values())
        topics_list = list(
            map(lambda topic_metadata: Topic(topic_metadata), raw_topics)
        )
        topics_list.sort(key=lambda topic: topic.name)
        return topics_list

    def protocol(self):
        default_protocol = "plain"

        if not self.config:
            return default_protocol

        if not self.config.kafka:
            return default_protocol

        protocol = self.config.kafka.get("security.protocol")

        return protocol.lower() if protocol else default_protocol

    def has_schemas(self):
        return bool(self.config) and bool(self.config.schema_registry)

    def brokers(self):
        topics_list = []

        if not self.config:
            return topics_list

        if not self.config.kafka:
            return topics_list

        admin_client = AdminClient(self.config.kafka)
        brokers_list = list(admin_client.list_topics(timeout=TIMEOUT).brokers.values())
        brokers_list.sort(key=lambda broker: broker.id)
        return brokers_list

    def version(self):
        default_version = "unknown"

        if not self.config:
            return default_version

        if not self.config.kafka:
            return default_version

        brokers = self.brokers()

        if not brokers:
            return default_version

        broker_id = str(brokers[0].id)

        admin_client = AdminClient(self.config.kafka)

        config_to_describe = [
            ConfigResource(confluent_kafka.admin.RESOURCE_BROKER, broker_id)
        ]
        future_config = admin_client.describe_configs(config_to_describe)
        future_as_completed = concurrent.futures.as_completed(
            iter(future_config.values())
        )
        task = next(future_as_completed)
        task_result = task.result(timeout=TIMEOUT)

        if not task_result:
            return default_version

        version = task_result.get("inter.broker.protocol.version")

        if not version:
            return default_version

        return version.value.split("-")[0]


class Topic:
    def __init__(self, topic_metadata):
        self.__topic_metadata = topic_metadata
        self.name = self.__topic_metadata.topic

    def __str__(self):
        return self.name

    def partitions(self):
        return list(self.__topic_metadata.partitions.values())


if __name__ == "__main__":

    class Config:
        kafka = {"bootstrap.servers": "localhost:9093"}
        schema_registry = {}

    config = Config()

    kafka = Kafka(config)

    print("> INFO:")
    print("has schemas:", kafka.has_schemas())
    print("protocol:", kafka.protocol())
    print("version:", kafka.version())

    print("\n> BROKERS:")
    for broker in kafka.brokers():
        print(broker.id, broker.host, broker.port)

    print("\n> TOPICS:")
    for topic in kafka.topics():
        print(topic.name)
        for partition in topic.partitions():
            print("\t", partition.replicas)
