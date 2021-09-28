import sys

from pyfiglet import Figlet
from rich.console import Console

from kaskade import kaskade_package
from kaskade.tui import Tui


class Cli:
    def __init__(self, dictionary):
        for k, v in dictionary.items():
            setattr(self, k, v)

    def run(self):
        self.option_version()
        self.run_tui()

    def run_tui(self):
        Tui.run(config={"bootstrap.servers": "localhost:19093"})

    def option_version(self):
        if self.version:
            figlet = Figlet(font="slant")
            console = Console()
            console.print(
                "[magenta]{}[/]".format(figlet.renderText(kaskade_package.name).rstrip())
            )
            console.print("[magenta]{}[/] [green]v{}[/]".format(kaskade_package.name, kaskade_package.version))
            console.print("{}".format(kaskade_package.documentation))
            sys.exit(0)
