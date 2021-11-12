import sys

from confluent_kafka import KafkaException
from rich.console import Console

from kaskade import APP_UI_LOG, logger
from kaskade.config import Config
from kaskade.emojis import THINKING_FACE
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.tui import Tui


class Cli:
    def __init__(self, print_version: bool, config_file: str) -> None:
        self.print_version = print_version
        self.config_file = config_file

    def run(self) -> None:
        try:
            self.print_version_option()
            self.run_tui()
        except Exception as ex:
            message = str(ex)

            if isinstance(ex, KafkaException):
                message = ex.args[0].str()

            console = Console()
            console.print(
                '{} [bold red]A problem has occurred[/] [bold green]"{}"[/]'.format(
                    THINKING_FACE, message
                )
            )
            logger.critical("Error starting the app: %s", message)
            logger.exception(ex)

            sys.exit(1)

    def print_version_option(self) -> None:
        if self.print_version:
            console = Console()
            console.print(KaskadeName())
            console.print(KaskadeVersion())
            sys.exit(0)

    def run_tui(self) -> None:
        config = Config(self.config_file)
        Tui.run(config=config, log=APP_UI_LOG if config.kaskade.get("log-ui") else None)
