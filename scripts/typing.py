from scripts import CommandProcessor


def main():
    commands = {
        "checking types :snake:": "poetry run mypy kaskade/",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
