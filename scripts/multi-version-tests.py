from scripts import CommandProcessor


def main():
    commands = {
        "executing multi-version tests :test_tube:": "poetry run tox -v",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
