import click

from kaskade.cli import Cli


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
