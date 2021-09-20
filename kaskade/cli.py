import click


class Cli:
    def __init__(self):
        pass


class CliOptions:
    def __init__(self):
        pass


@click.command()
@click.option("--version", is_flag=True, help="Show the app version.")
def main(version):
    """
    kaskade is a terminal user interface for kafka.
    Example: kaskade.
    """
    pass


if __name__ == "__main__":
    main()
