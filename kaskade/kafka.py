from confluent_kafka.admin import AdminClient


class Kafka:
    def __init__(self, config):
        self.config = config

    def topics(self):
        admin_client = AdminClient(self.config)
        raw_topics = list(admin_client.list_topics(timeout=1).topics.values())
        topics_list = list(
            map(lambda topic_metadata: Topic(topic_metadata), raw_topics)
        )
        topics_list.sort(key=lambda topic: topic.name)
        return topics_list


class Topic:
    def __init__(self, topic_metadata):
        self.__topic_metadata = topic_metadata
        self.name = self.__topic_metadata.topic

    def __str__(self):
        return self.name

    @property
    def partitions(self):
        return list(self.__topic_metadata.partitions.values())


if __name__ == "__main__":
    localhost_config = {"bootstrap.servers": "localhost:19093"}
    kafka = Kafka(localhost_config)
    for topic in kafka.topics():
        print(topic)
        for partition in topic.partitions:
            print("\t", partition.replicas)
