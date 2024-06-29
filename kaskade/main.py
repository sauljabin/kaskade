import sys

import click

from kaskade import APP_VERSION
from kaskade.consumer import KaskadeConsumer
from kaskade.admin import KaskadeAdmin
from kaskade.models import Format

SR_URL_MESSAGE_VALIDATION = """Usage: kaskade consumer [OPTIONS]
Try 'kaskade consumer --help' for help.

Error: Missing option '-s url=<my url>'"""

SR_AVRO_FORMAT_VALIDATION = """Usage: kaskade consumer [OPTIONS]
Try 'kaskade consumer --help' for help.

Error: Missing option '-k avro' and/or '-v avro'"""


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
    "-x",
    "kafka_properties_input",
    help="Kafka property. Set a librdkafka configuration property. Multiple -x are allowed.",
    metavar="property=value",
    multiple=True,
)
@click.option(
    "-t",
    "topic",
    help="Topic.",
    metavar="name",
    required=True,
)
@click.option(
    "-k",
    "key_format_str",
    type=click.Choice(Format.str_list(), False),
    help="Key format.",
    default=str(Format.BYTES),
    show_default=True,
)
@click.option(
    "-v",
    "value_format_str",
    type=click.Choice(Format.str_list(), False),
    help="Value format.",
    default=str(Format.BYTES),
    show_default=True,
)
@click.option(
    "-s",
    "registry_properties_input",
    help="Schema Registry property. Set a SchemaRegistryClient property. Multiple -s are allowed. Needed if -k avro "
    "or -v avro were passed.",
    metavar="property=value",
    multiple=True,
)
def consumer(
    bootstrap_servers_input: str,
    kafka_properties_input: tuple[str, ...],
    registry_properties_input: tuple[str, ...],
    topic: str,
    key_format_str: str,
    value_format_str: str,
) -> None:
    """

    kaskade consumer mode.

    \b
    Examples:
        kaskade consumer -b localhost:9092 -t my-topic
        kaskade consumer -b localhost:9092 -t my-topic -v json
        kaskade consumer -b localhost:9092 -t my-topic -x auto.offset.reset=earliest
        kaskade consumer -b localhost:9092 -t my-topic -s url=http://localhost:8081 -v avro

    More at https://github.com/sauljabin/kaskade.
    """
    kafka_conf = {k: v for (k, v) in [pair.split("=", 1) for pair in kafka_properties_input]}
    kafka_conf["bootstrap.servers"] = bootstrap_servers_input
    schemas_conf = {k: v for (k, v) in [pair.split("=", 1) for pair in registry_properties_input]}
    key_format = Format.from_str(key_format_str)
    value_format = Format.from_str(value_format_str)

    if len(schemas_conf) > 0 and schemas_conf.get("url") is None:
        print(SR_URL_MESSAGE_VALIDATION)
        sys.exit(1)

    if len(schemas_conf) == 0 and (key_format == Format.AVRO or value_format == Format.AVRO):
        print(SR_URL_MESSAGE_VALIDATION)
        sys.exit(1)

    if len(schemas_conf) > 0 and key_format != Format.AVRO and value_format != Format.AVRO:
        print(SR_AVRO_FORMAT_VALIDATION)
        sys.exit(1)

    kaskade_app = KaskadeConsumer(topic, kafka_conf, schemas_conf, key_format, value_format)
    kaskade_app.run()


if __name__ == "__main__":
    cli()
