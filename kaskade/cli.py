import sys

from pyfiglet import Figlet
from rich.console import Console

from kaskade import kaskade_package
from kaskade.config import Config
from kaskade.tui import Tui


class Cli:
    def __init__(self, print_version=False, config_file=None):
        self.print_version = print_version
        self.config_file = config_file

    def run(self):
        self.option_version()
        self.run_tui()

    def run_tui(self):
        Tui.run(config=Config(self.config_file))

    def option_version(self):
        if self.print_version:
            figlet = Figlet(font="slant")
            console = Console()
            console.print(
                "[magenta]{}[/]".format(
                    figlet.renderText(kaskade_package.name).rstrip()
                )
            )
            console.print(
                "[magenta]{}[/] [green]v{}[/]".format(
                    kaskade_package.name, kaskade_package.version
                )
            )
            console.print("{}".format(kaskade_package.documentation))
            sys.exit(0)
