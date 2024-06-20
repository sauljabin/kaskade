import sys
from typing import Tuple

import click
from confluent_kafka import KafkaException
from rich.console import Console
from textual.app import ComposeResult, App

from kaskade import APP_VERSION
from kaskade.widgets import Header


class KaskadeApp(App):
    CSS_PATH = "app.css"

    def __init__(self, kafka_conf: dict[str, str], registry_conf: dict[str, str]):
        super().__init__()
        self.kafka_conf = kafka_conf
        self.registry_conf = registry_conf

    def compose(self) -> ComposeResult:
        self.log.debug(f"Kafka config: {self.kafka_conf}\nRegistry config: {self.registry_conf}")
        yield Header()


@click.command(epilog="More info at https://github.com/sauljabin/kaskade.")
@click.version_option(APP_VERSION)
@click.option(
    "-b",
    "bootstrap_servers_input",
    help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092. ",
    metavar="host:port",
    required=True,
)
@click.option(
    "-S",
    "registry_properties_input",
    help="Schema Registry property. Set a SchemaRegistryClient property. Multiple -S are allowed.",
    metavar="property=value",
    multiple=True,
)
@click.option(
    "-X",
    "kafka_properties_input",
    help="Kafka property. Set a librdkafka configuration property. Multiple -X are allowed.",
    metavar="property=value",
    multiple=True,
)
def main(
        bootstrap_servers_input: str,
        kafka_properties_input: Tuple[str],
        registry_properties_input: Tuple[str],
) -> None:
    """

    kaskade is a terminal user interface for kafka.

    \b
    Examples:
        kaskade -b localhost:9092
        kaskade -b broker1:9092,broker2:9092
        kaskade -b localhost:9092 -X security.protocol=SSL
        kaskade -b localhost:9092 -S url=http://localhost:8081
    """
    kafka_conf = {k: v for (k, v) in [pair.split("=") for pair in kafka_properties_input]}
    kafka_conf["bootstrap.servers"] = bootstrap_servers_input
    registry_conf = {k: v for (k, v) in [pair.split("=") for pair in registry_properties_input]}

    try:
        kaskade_app = KaskadeApp(kafka_conf, registry_conf)
        kaskade_app.run()
    except Exception as ex:
        if isinstance(ex, KafkaException):
            message = ex.args[0].str()
        else:
            message = str(ex)

        console = Console()
        console.print(f'[bold red]A problem has occurred: "{message}"[/]')
        sys.exit(1)


if __name__ == "__main__":
    main()
