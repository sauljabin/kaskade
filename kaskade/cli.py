import sys
from logging import DEBUG

from confluent_kafka import KafkaException
from rich.console import Console

from kaskade import logger
from kaskade.config import Config
from kaskade.emojis import THINKING_FACE
from kaskade.renderables.config_examples import ConfigExamples
from kaskade.renderables.kaskade_info import KaskadeInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.tui import Tui


class Cli:
    def __init__(
        self, print_version: bool, print_information: bool, config_file: str
    ) -> None:
        self.print_version = print_version
        self.print_information = print_information
        self.config_file = config_file

    def run(self) -> None:
        try:
            self.print_version_option()
            self.print_information_option()
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

    def print_information_option(self) -> None:
        if not self.print_information:
            return

        console = Console()
        console.print(KaskadeName())
        console.print()
        console.print(KaskadeInfo())
        console.print()
        console.print(ConfigExamples())

        sys.exit(0)

    def print_version_option(self) -> None:
        if not self.print_version:
            return

        console = Console()
        console.print(KaskadeName())
        console.print(KaskadeVersion())

        sys.exit(0)

    def run_tui(self) -> None:
        config = Config(self.config_file)
        is_debug = bool(config.kaskade.get("debug"))

        if is_debug:
            logger.setLevel(DEBUG)
            logger.debug("Starting in debug mode")

        logger.debug("Starting TUI")
        Tui.run(config=config)
