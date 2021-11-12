import click

from kaskade.cli import Cli


@click.command()
@click.option("--version", is_flag=True, help="Show the app version and exit.")
@click.option(
    "--info", is_flag=True, help="Show the app information and config examples."
)
@click.argument(
    "config_file", metavar="<config file>", nargs=1, required=False, default=""
)
def main(version: bool, info: bool, config_file: str) -> None:
    """

    kaskade is a terminal user interface for kafka.

    \b
    It receives an argument <config file>, in case of not
    passing any argument it'll take any of next config file
    names in the current path by default:
        kaskade.yml, kaskade.yaml, config.yml or config.yaml.

    \b
    Examples:
        kaskade
        kaskade my-config.yml

    More info at https://github.com/sauljabin/kaskade.
    """
    cli = Cli(print_version=version, print_information=info, config_file=config_file)
    cli.run()


if __name__ == "__main__":
    main()
