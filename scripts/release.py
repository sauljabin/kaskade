import click
import toml

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
    # agregar todos los cambios
    # agregar tag de la version actual
    # push tag

    validations_commands = {
        "checking if there are pending changes :checkered_flag:": "git diff --exit-code",
        "checking if there are pending changes in stage": "git diff --staged --exit-code",
        "checking if there are not pushed commits :kite:": "git diff --exit-code main origin/main",
        f"bumping [yellow bold]{rule}[/] version": f"poetry version {rule}",
    }
    command_processor = CommandProcessor(validations_commands)
    command_processor.run()

    version = get_current_version()

    commands = {
        "adding new version": "git add --all",
        "committing new version": f"git commit -m 'bumping version to {version}'",
        "adding new version tag": f"git tag {version}",
        "pushing new changes :boom:": f"git tag {version}",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


def get_current_version():
    toml_data = toml.load("pyproject.toml")
    return toml_data["tool"]["poetry"]["version"]


if __name__ == "__main__":
    main()
