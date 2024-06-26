import random

import click
from confluent_kafka.cimpl import NewTopic

from kaskade.services import TopicService


@click.command()
@click.option(
    "-b",
    "bootstrap_servers_input",
    help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092. ",
    metavar="host:port",
    required=True,
    default="localhost:19092",
)
def main(bootstrap_servers_input: str):
    topic_service = TopicService({"bootstrap.servers": bootstrap_servers_input})
    for i in range(61, 101):
        topic_service.create(
            NewTopic(f"kaskade.test.{i}", random.randint(10, 20), replication_factor=3)
        )


if __name__ == "__main__":
    main()
