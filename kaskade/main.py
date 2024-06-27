import sys

import click
from confluent_kafka import KafkaException
from rich.console import Console

from kaskade import APP_VERSION
from kaskade.consumer import KaskadeConsumer
from kaskade.admin import KaskadeAdmin
from kaskade.models import Format


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
    help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092.",
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
    kafka_properties_input: tuple[str, ...],
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
    help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092.",
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
    "-x",
    "kafka_properties_input",
    help="Kafka property. Set a librdkafka configuration property. Multiple -x are allowed.",
    metavar="property=value",
    multiple=True,
)
@click.option(
    "-k",
    "key_format",
    type=click.Choice([key_format.name.lower() for key_format in Format], False),
    help="Key format.",
    default=Format.BYTES.name.lower(),
    show_default=True,
)
@click.option(
    "-v",
    "value_format",
    type=click.Choice([key_format.name.lower() for key_format in Format], False),
    help="Value format.",
    default=Format.BYTES.name.lower(),
    show_default=True,
)
def consumer(
    bootstrap_servers_input: str,
    kafka_properties_input: tuple[str, ...],
    topic: str,
    key_format: str,
    value_format: str,
) -> None:
    """

    kaskade consumer mode.

    \b
    Examples:
        kaskade -b localhost:9092 -t my-topic
        kaskade -b localhost:9092 -t my-topic -x auto.offset.reset=earliest

    More at https://github.com/sauljabin/kaskade.
    """
    kafka_conf = {k: v for (k, v) in [pair.split("=", 1) for pair in kafka_properties_input]}
    kafka_conf["bootstrap.servers"] = bootstrap_servers_input

    kaskade_app = KaskadeConsumer(
        topic, kafka_conf, Format.from_str(key_format), Format.from_str(value_format)
    )
    kaskade_app.run()


if __name__ == "__main__":
    cli()
