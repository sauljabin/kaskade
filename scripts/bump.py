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
        poetry run python -m scripts.bump major
        poetry run python -m scripts.bump minor
        poetry run python -m scripts.bump patch

    More info at https://python-poetry.org/docs/cli/#version and https://semver.org/.
    """
    bump_version(rule)
    new_app_version = get_app_version()
    changelog_release(new_app_version)

    console = Console()
    confirmation = console.input(
        f"\n[bold]Release a new [purple]{rule}[/] version [purple]{new_app_version}[/]"
        " ([green]yes[/]/[red]no[/])? [/]"
    )

    if confirmation != "yes":
        revert_changes()
        exit(1)

    confirm_changes(new_app_version)


def changelog_release(version):
    init_commands = {
        f"upgrading changelog to a [purple bold]{version}[/] version": (
            f"poetry run changeloggh release {version}"
        ),
    }
    revert_commands = {
        "deleting changes": "git checkout .",
    }
    command_processor = CommandProcessor(init_commands, revert_commands)
    command_processor.run()


def bump_version(rule):
    init_commands = {
        "checking pending changes": "git diff --exit-code",
        "checking pending changes in stage": "git diff --staged --exit-code",
        "checking not pushed commits": "git diff --exit-code main origin/main",
        f"upgrading to a [purple bold]{rule}[/] version": f"poetry version {rule}",
    }
    command_processor = CommandProcessor(init_commands)
    command_processor.run()


def confirm_changes(app_version):
    confirm_commands = {
        "adding new version": "git add --all",
        "committing new version": f"git commit -m 'upgrading version to {app_version}'",
        "adding new version tag": f"git tag v{app_version}",
        "pushing new changes": "git push origin main",
        "pushing tag": "git push --tags",
    }
    command_processor = CommandProcessor(confirm_commands)
    command_processor.run()


def revert_changes():
    revert_commands = {
        "deleting changes": "git checkout .",
    }
    command_processor = CommandProcessor(revert_commands)
    command_processor.run()


def get_app_version():
    toml_data = toml.load("pyproject.toml")
    app_version = toml_data["tool"]["poetry"]["version"]
    return app_version


if __name__ == "__main__":
    main()
