import click

from scripts import CommandProcessor


@click.command()
@click.option("--e2e", "e2e", is_flag=True, help="Run e2e tests.")
def main(e2e: bool) -> None:
    module = "tests-e2e" if e2e else "tests"
    commands = {
        "executing tests": f"poetry run python -m unittest discover -v {module}",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
