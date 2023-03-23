from scripts import CommandProcessor


def main():
    commands = {
        "tests coverage": "poetry run coverage run -m unittest -v",
        "coverage report": "poetry run coverage report -m",
        "coverage report html": "poetry run coverage html",
        "coverage report xml": "poetry run coverage xml",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
