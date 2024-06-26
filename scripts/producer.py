import click
from confluent_kafka.cimpl import NewTopic, Producer

from kaskade.services import TopicService

TOPIC_STRING = "kaskade.strings"


def delivery_report(err, msg):
    if err is not None:
        print(f"error producing to: {msg.topic()}: {msg.key()}")


@click.command()
@click.option(
    "-b",
    "bootstrap_servers_input",
    help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092.",
    metavar="host:port",
    required=True,
    default="localhost:19092",
)
@click.option(
    "-c",
    "create_topics",
    help="Create topics.",
    is_flag=True,
)
def main(bootstrap_servers_input: str, create_topics: bool):
    config = {"bootstrap.servers": bootstrap_servers_input}
    topic_service = TopicService(config)
    producer = Producer(config)

    # CREATE TOPICS
    if create_topics:
        print("creating topics")
        topics = [NewTopic(TOPIC_STRING, 5, replication_factor=3)]
        topic_service.create(topics)

    # PRODUCE TO STRING TOPIC
    print("start producing to", TOPIC_STRING)
    for i in range(1, 101):
        value = f"value {i}"
        key = f"key {i}"
        headers = {f"{TOPIC_STRING}": f"message {i}"}
        producer.produce(
            TOPIC_STRING, value=value, key=key, headers=headers, on_delivery=delivery_report
        )
        producer.poll(0)

    producer.flush()


if __name__ == "__main__":
    main()
