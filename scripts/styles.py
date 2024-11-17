from scripts import CommandProcessor


def main() -> None:
    commands = {
        "black": "poetry run black . --preview",
        "ruff": "poetry run ruff check . --fix",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
