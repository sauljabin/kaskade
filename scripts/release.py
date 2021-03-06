import datetime
import sys

import click
import toml
from rich.console import Console

from scripts import CommandProcessor


@click.command()
@click.argument(
    "rule",
    nargs=1,
    type=click.Choice(["major", "minor", "patch"], case_sensitive=False),
)
def main(rule):
    """
    \b
    Examples:
        poetry run python -m scripts.release major
        poetry run python -m scripts.release minor
        poetry run python -m scripts.release patch

    More info at https://python-poetry.org/docs/cli/#version and https://semver.org/.
    """
    validations_commands = {
        "checking if there are pending changes :checkered_flag:": "git diff --exit-code",
        "checking if there are pending changes in stage": "git diff --staged --exit-code",
        "checking if there are not pushed commits :kite:": "git diff --exit-code main origin/main",
        f"bumping [purple bold]{rule}[/] version": f"poetry version {rule}",
    }
    command_processor = CommandProcessor(validations_commands)
    command_processor.run()

    toml_data = toml.load("pyproject.toml")
    version = toml_data["tool"]["poetry"]["version"]

    console = Console()

    with open("CHANGELOG.md", "r") as file:
        changelog = file.read()

    date = datetime.date.today()
    changelog_entry = f"## [{version}] - {date}"

    if changelog_entry not in changelog:
        console.print(
            f'\n[bold red]Error:exclamation:[/] changelog entry "[bold yellow]{changelog_entry}[/]" not found'
        )
        sys.exit(1)

    confirmation = console.input(
        f"Release a new [purple bold]{rule}[/] version [bold purple]{version}[/] "
        f"([bold green]yes[/]/[bold red]no[/])? "
    )

    if confirmation != "yes":
        commands = {
            "deleting changes": "git checkout .",
        }
        command_processor = CommandProcessor(commands)
        command_processor.run()
        return

    commands = {
        "adding new version": "git add --all",
        "committing new version": f"git commit -m 'bumping version to {version}'",
        "adding new version tag": f"git tag v{version}",
        "pushing new changes :boom:": "git push origin main",
        "pushing tag": "git push --tags",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
