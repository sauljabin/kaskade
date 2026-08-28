from scripts import CommandProcessor


def main() -> None:
    commands = {
        "checking types": "mypy kaskade/ scripts/",
        "black": "black --check .",
        "ruff": "ruff check .",
        "typos": "typos --format brief",
        "github actions": "actionlint",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
