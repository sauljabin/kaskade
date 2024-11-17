import time

from confluent_kafka.cimpl import NewTopic
from typing import Callable, Any
import uuid

import click
from kaskade.configs import BOOTSTRAP_SERVERS
from rich.console import Console
from confluent_kafka.admin import AdminClient
from confluent_kafka import Producer, KafkaError, KafkaException
from faker import Faker

from kaskade.utils import pack_bytes

FAKER = Faker()
TOPICS = [
    (
        "string",
        lambda: FAKER.name(),
        lambda value: value.encode("utf-8"),
    ),
    (
        "integer",
        lambda: FAKER.pyint(min_value=500, max_value=10000),
        lambda value: pack_bytes(">i", value),
    ),
    (
        "long",
        lambda: FAKER.pyint(min_value=500, max_value=10000),
        lambda value: pack_bytes(">q", value),
    ),
    (
        "float",
        lambda: FAKER.pyfloat(min_value=500, max_value=10000),
        lambda value: pack_bytes(">f", value),
    ),
    (
        "double",
        lambda: FAKER.pyfloat(min_value=500, max_value=10000),
        lambda value: pack_bytes(">d", value),
    ),
    (
        "boolean",
        lambda: FAKER.pybool(),
        lambda value: pack_bytes(">?", value),
    ),
    (
        "json",
        lambda: FAKER.json(),
        lambda value: value.encode("utf-8"),
    ),
]


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
            try:
                future.result()
            except KafkaException as ke:
                if (
                    len(ke.args) > 0
                    and hasattr(ke.args[0], "code")
                    and ke.args[0].code() is not KafkaError.TOPIC_ALREADY_EXISTS
                ):
                    raise ke

    def populate(
        self,
        topic: str,
        generator: Callable[[], Any],
        serializer: Callable[[Any], Any],
        total_messages: int,
    ) -> None:
        for n in range(total_messages):
            value = generator()
            self.producer.produce(topic, value=serializer(value), key=f"{value}")
        self.producer.flush(5)


@click.command()
@click.option("--messages", default=1000, help="Number of messages to initialize.")
def main(messages: int) -> None:
    populator = Populator({BOOTSTRAP_SERVERS: "localhost:19092"})
    console = Console()
    with console.status("", spinner="dots") as status:
        for topic, generator, serializer in TOPICS:
            start = time.time()
            status.update(f" [yellow]populating topic:[/] {topic}")
            populator.create_topic(topic)
            populator.populate(topic, generator, serializer, messages)
            console.print(f":white_check_mark: {topic} [green]{time.time() - start:.1f} secs[/]")


if __name__ == "__main__":
    main()
