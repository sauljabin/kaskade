from scripts import CommandProcessor


def main():
    commands = {
        "executing pre-commit hooks": "poetry run pre-commit run --all-files",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
