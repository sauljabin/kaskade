from scripts import CommandProcessor


def main() -> None:
    commands = {
        "black": "black . --preview",
        "ruff": "ruff check . --fix",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
