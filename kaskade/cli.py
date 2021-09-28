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
        self.run_tui()

    def run_tui(self):
        Kaskade.run(config={"bootstrap.servers": "localhost:19093"})

    def option_version(self):
        if self.version:
            figlet = Figlet(font="slant")
            console = Console()
            console.print(
                "[magenta]{}[/]".format(figlet.renderText(kaskade_package.name))
            )
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
