import sys

from rich.console import Console

from kaskade import logger
from kaskade.config import Config
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.tui import Tui


class Cli:
    def __init__(self, print_version: bool, config_file: str) -> None:
        self.print_version = print_version
        self.config_file = config_file

    def run(self) -> None:
        try:
            if self.print_version:
                self.option_version()
                sys.exit(0)
            self.run_tui()
        except Exception as ex:
            console = Console()
            console.print(
                ":thinking_face: [bold red]A problem has occurred[/]: {}".format(ex)
            )
            logger.critical("Error starting the app: %s", ex)
            sys.exit(1)

    def run_tui(self) -> None:
        Tui.run(config=Config(self.config_file))

    def option_version(self) -> None:
        console = Console()
        console.print(KaskadeName())
        console.print(KaskadeVersion())
