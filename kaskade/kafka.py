from confluent_kafka.admin import AdminClient


class Kafka:
    def __init__(self, config):
        self.config = config

    def topics(self):
        admin_client = AdminClient(self.config)
        return admin_client.list_topics(timeout=1).topics


if __name__ == "__main__":
    kafka = Kafka({"bootstrap.servers": "localhost:19093"})
    topics = kafka.topics()
    sorted_topics = dict(sorted(topics.items(), key=lambda item: item[0]))
    print(topics)
    print(sorted_topics)
    print(len(sorted_topics))
    for index, val in enumerate(sorted_topics):
        print(index, val)
    print(list(sorted_topics.items())[0])
    print(list(sorted_topics.items())[0][1].partitions)
    for id, partition in list(sorted_topics.items())[0][1].partitions.items():
        print(partition.replicas)
