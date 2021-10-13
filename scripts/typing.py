import click

from scripts import CommandProcessor


@click.command()
@click.argument("path", nargs=1, default="kaskade/")
def main(path):
    commands = {
        "checking types :snake:": "poetry run mypy {}".format(path),
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
