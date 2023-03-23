from scripts import CommandProcessor


def main():
    commands = {
        "black": "poetry run black . --preview",
        "ruff": "poetry run ruff . --fix",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
