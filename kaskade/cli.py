import sys

from rich.console import Console

from kaskade.config import Config
from kaskade.kaskade import Kaskade
from kaskade.tui import Tui


class Cli:
    def __init__(self, print_version=False, config_file=None):
        self.print_version = print_version
        self.config_file = config_file

    def run(self):
        try:
            self.option_version()
            self.run_tui()
        except Exception as ex:
            console = Console()
            console.print(
                ":thinking_face: [bold red]A problem has occurred[/]: {}".format(
                    str(ex)
                )
            )

    def run_tui(self):
        Tui.run(config=Config(self.config_file))

    def option_version(self):
        if self.print_version:
            kaskade = Kaskade()
            console = Console()
            console.print(kaskade.riched_name())
            console.print(kaskade.riched_version())
            sys.exit(0)
