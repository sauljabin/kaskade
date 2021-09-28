import sys

import click
from pyfiglet import Figlet
from rich.console import Console

from kaskade import kaskade_package
from kaskade.tui import Kaskade


class Cli:
    def __init__(self, dictionary):
        for k, v in dictionary.items():
            setattr(self, k, v)

    def run(self):
        self.option_version()
        self.init_tui()

    def init_tui(self):
        kaskade = Kaskade()
        kaskade.init()

    def option_version(self):
        if self.version:
            fig = Figlet(font="slant")
            console = Console()
            console.print("[magenta]{}[/]".format(fig.renderText(kaskade_package.name)))
            console.print("Version: {}".format(kaskade_package.version))
            console.print("Doc: {}".format(kaskade_package.documentation))
            sys.exit(0)


@click.command()
@click.option("--version", is_flag=True, help="Show the app version.")
def main(version):
    """
    kaskade is a terminal user interface for kafka.
    Example: kaskade.
    """
    cli = Cli({"version": version})
    cli.run()


if __name__ == "__main__":
    main()
