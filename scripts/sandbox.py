from confluent_kafka.cimpl import NewTopic
from typing import Callable
import uuid

import click
from kaskade.configs import BOOTSTRAP_SERVERS
from rich.console import Console
from confluent_kafka.admin import AdminClient
from confluent_kafka import Producer
from faker import Faker


TOPICS_TMP = ["string", "integer", "long", "float", "double", "boolean"]
FAKER = Faker()
TOPICS = {"string": lambda: FAKER.name().encode("utf-8")}


class Populator:
    def __init__(self, kafka_config: dict[str, str]) -> None:
        self.producer = Producer(
            kafka_config
            | {
                "client.id": f"{uuid.uuid4()}",
            }
        )
        self.admin_client = AdminClient(kafka_config)

    def create_topic(self, topic: str) -> None:
        futures = self.admin_client.create_topics([NewTopic(topic)])
        for future in futures.values():
            future.result()

    def populate(self, topic: str, generator: Callable[[], bytes], total_messages: int) -> None:
        for n in range(total_messages):
            self.producer.produce(topic, value=generator(), key=f"{n}")

    def close(self) -> None:
        self.producer.flush(1)


@click.command()
@click.option("--messages", default=1000, help="Number of messages to initialize.")
def main(messages: int) -> None:
    populator = Populator({BOOTSTRAP_SERVERS: "localhost:19092"})

    with Console().status("", spinner="dots") as status:
        for topic, generator in TOPICS.items():
            status.update(f" Creating topic: {topic}")
            populator.create_topic(topic)
            populator.populate(topic, generator, messages)

    populator.close()


if __name__ == "__main__":
    main()
