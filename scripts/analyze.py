from scripts import CommandProcessor


def main() -> None:
    commands = {
        "checking types": "poetry run mypy kaskade/ scripts/",
        "black": "poetry run black --check .",
        "ruff": "poetry run ruff check .",
        "typos": "poetry run typos --format brief",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
