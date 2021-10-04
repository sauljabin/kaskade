from scripts import CommandProcessor


def main():
    commands = {
        "removing unused imports": "poetry run autoflake --in-place --remove-all-unused-imports -r .",
        "sort imports": "poetry run isort .",
        "applying styles :wrench:": "poetry run black .",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
