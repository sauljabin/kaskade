import click

from kaskade.cli import Cli


@click.command()
@click.option("--version", is_flag=True, help="Show the app version and exit.")
@click.argument(
    "config_file", metavar="<config file>", nargs=1, required=False, default=""
)
def main(version: bool, config_file: str) -> None:
    """

    kaskade is a terminal user interface for kafka.

    \b
    It receives an argument <config file>, in case of not passing
    any argument it'll take any of next config file names by default:
    kaskade.yml, kaskade.yaml, config.yml, config.yaml.

    More info at https://github.com/sauljabin/kaskade.

    \b
    Examples:
        kaskade
        kaskade config.yml
    """
    cli = Cli(print_version=version, config_file=config_file)
    cli.run()


if __name__ == "__main__":
    main()
