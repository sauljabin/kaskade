import click

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
        Consumes a topic.
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

    kaskade admin mode allows you to manage topics.

    \b
    Examples:
        kaskade admin -b localhost:9092
        kaskade admin -b localhost:9092 -x security.protocol=SSL

    More at https://github.com/sauljabin/kaskade.
    """
    kafka_conf = {k: v for (k, v) in [pair.split("=", 1) for pair in kafka_properties_input]}
    kafka_conf["bootstrap.servers"] = bootstrap_servers_input

    kaskade_app = KaskadeAdmin(kafka_conf)
    kaskade_app.run()


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
    type=click.Choice(Format.str_list(), False),
    help="Key format.",
    default=str(Format.BYTES),
    show_default=True,
)
@click.option(
    "-v",
    "value_format",
    type=click.Choice(Format.str_list(), False),
    help="Value format.",
    default=str(Format.BYTES),
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
        kaskade consumer -b localhost:9092 -t my-topic
        kaskade consumer -b localhost:9092 -t my-topic -v json
        kaskade consumer -b localhost:9092 -t my-topic -x auto.offset.reset=earliest

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
