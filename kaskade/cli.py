import click
from pyfiglet import Figlet

from kaskade import __version__, repository


class Cli:
    def __init__(self, options):
        self.options = options

    def run(self):
        if self.options.version:
            fig = Figlet(font="slant")
            click.echo(fig.renderText("kaskade"))
            click.echo("Version: {}".format(__version__))
            click.echo("Doc: {}".format(repository))


class CliOptions:
    def __init__(self, dictionary):
        for k, v in dictionary.items():
            setattr(self, k, v)


@click.command()
@click.option("--version", is_flag=True, help="Show the app version.")
def main(version):
    """
    kaskade is a terminal user interface for kafka.
    Example: kaskade.
    """
    cli_options = CliOptions({"version": version})
    cli = Cli(cli_options)
    cli.run()


if __name__ == "__main__":
    main()
