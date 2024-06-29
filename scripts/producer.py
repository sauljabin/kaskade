import json
from time import sleep

import click
from confluent_kafka.cimpl import NewTopic, Producer
from confluent_kafka.serialization import DoubleSerializer, IntegerSerializer
from faker import Faker

from kaskade.services import TopicService

TOPIC_STRING = "kaskade.string"
TOPIC_JSON = "kaskade.json"
TOPIC_INTEGER = "kaskade.integer"
TOPIC_DOUBLE = "kaskade.double"


def delivery_report(err, msg):
    if err is not None:
        print(f"error producing to: {msg.topic()}: {msg.key()}")


def make_new_topic(name):
    return NewTopic(name, 5, replication_factor=3)


def produce_jsons(config):
    producer = Producer(config)
    faker = Faker()
    print("start producing to", TOPIC_JSON)
    for i in range(1, 101):
        key = json.dumps({"id": faker.uuid4()}, indent=4)
        value = json.dumps(
            {"name": faker.name(), "address": faker.address(), "phone": faker.phone_number()},
            indent=4,
        )
        producer.produce(TOPIC_JSON, value=value, key=key, on_delivery=delivery_report)
        producer.poll(0)
        producer.flush()


def produce_strings(config):
    producer = Producer(config)
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


def produce_integers(config):
    producer = Producer(config)
    faker = Faker()
    serializer = IntegerSerializer()
    print("start producing to", TOPIC_INTEGER)
    for i in range(1, 101):
        headers = {f"{TOPIC_INTEGER}": f"message {i}"}
        value = faker.pyint()
        producer.produce(
            TOPIC_INTEGER, value=serializer(value), headers=headers, on_delivery=delivery_report
        )
        producer.poll(0)
        producer.flush()


def produce_doubles(config):
    producer = Producer(config)
    faker = Faker()
    serializer = DoubleSerializer()
    print("start producing to", TOPIC_DOUBLE)
    for i in range(1, 101):
        value = faker.pyfloat()
        producer.produce(TOPIC_DOUBLE, value=serializer(value), on_delivery=delivery_report)
        producer.poll(0)
        producer.flush()


def create_all_topics(config):
    topic_service = TopicService(config)
    print("creating topics")
    topics = [
        make_new_topic(TOPIC_STRING),
        make_new_topic(TOPIC_JSON),
        make_new_topic(TOPIC_INTEGER),
        make_new_topic(TOPIC_DOUBLE),
    ]
    topic_service.create(topics)


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

    if create_topics:
        create_all_topics(config)
        sleep(1)

    produce_strings(config)
    produce_jsons(config)
    produce_integers(config)
    produce_doubles(config)


if __name__ == "__main__":
    main()
