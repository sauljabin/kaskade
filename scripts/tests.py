from scripts import CommandProcessor


def main() -> None:
    commands = {
        "executing tests": "poetry run python -m unittest -v",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
