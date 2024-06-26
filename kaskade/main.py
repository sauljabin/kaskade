import sys
from typing import Tuple

import click
from confluent_kafka import KafkaException
from rich.console import Console

from kaskade import APP_VERSION
from kaskade.consumer import KaskadeConsumer
from kaskade.admin import KaskadeAdmin


@click.group()
@click.version_option(APP_VERSION)
def cli() -> None:
    """

    kaskade is a terminal user interface for kafka.

    \b
    Admin mode:
        Allows you to list and search topics.
        Run <kaskade admin --help> for more information.

    \b
    Consumer mode:
        Consumes for a topic.
        Run <kaskade consumer --help> for more information.

    More at https://github.com/sauljabin/kaskade.
    """
    pass


@cli.command()
@click.option(
    "-b",
    "bootstrap_servers_input",
    help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092. ",
    metavar="host:port",
    required=True,
)
@click.option(
    "-x",
    "kafka_properties_input",
    help="Kafka property. Set a librdkafka configuration property. Multiple -x are allowed.",
    metavar="property=value",
    multiple=True,
)
def admin(
    bootstrap_servers_input: str,
    kafka_properties_input: Tuple[str],
) -> None:
    """

    kaskade admin mode allows you to list topics and see their settings.

    \b
    Examples:
        kaskade admin -b localhost:9092
        kaskade admin -b localhost:9092 -x security.protocol=SSL

    More at https://github.com/sauljabin/kaskade.
    """
    kafka_conf = {k: v for (k, v) in [pair.split("=", 1) for pair in kafka_properties_input]}
    kafka_conf["bootstrap.servers"] = bootstrap_servers_input

    try:
        kaskade_app = KaskadeAdmin(kafka_conf)
        kaskade_app.run()
    except Exception as ex:
        if isinstance(ex, KafkaException):
            message = ex.args[0].str()
        else:
            message = str(ex)

        console = Console()
        console.print(f'[bold red]A problem has occurred: "{message}"[/]')
        sys.exit(1)


@cli.command()
@click.option(
    "-b",
    "bootstrap_servers_input",
    help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092. ",
    metavar="host:port",
    required=True,
)
@click.option(
    "-t",
    "topic",
    help="Topic.",
    metavar="name",
    required=True,
)
@click.option(
    "-s",
    "registry_properties_input",
    help="Schema Registry property. Set a SchemaRegistryClient property. Multiple -s are allowed.",
    metavar="property=value",
    multiple=True,
)
@click.option(
    "-x",
    "kafka_properties_input",
    help="Kafka property. Set a librdkafka configuration property. Multiple -x are allowed.",
    metavar="property=value",
    multiple=True,
)
def consumer(
    bootstrap_servers_input: str,
    kafka_properties_input: Tuple[str],
    registry_properties_input: Tuple[str],
    topic: str,
) -> None:
    """

    kaskade consumer mode.

    \b
    Examples:
        kaskade -b localhost:9092 -t my-topic
        kaskade -b localhost:9092 -t my-topic -x auto.offset.reset=earliest
        kaskade -b localhost:9092 -t my-topic -s url=http://localhost:8081

    More at https://github.com/sauljabin/kaskade.
    """
    kafka_conf = {k: v for (k, v) in [pair.split("=", 1) for pair in kafka_properties_input]}
    kafka_conf["bootstrap.servers"] = bootstrap_servers_input
    schemas_conf = {k: v for (k, v) in [pair.split("=", 1) for pair in registry_properties_input]}

    kaskade_app = KaskadeConsumer(topic, kafka_conf, schemas_conf)
    kaskade_app.run()


if __name__ == "__main__":
    cli()
