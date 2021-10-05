from scripts import CommandProcessor


def main():
    commands = {
        "checking imports": "poetry run isort --check .",
        "checking styles :magnifying_glass_tilted_left:": "poetry run black --check .",
        "checking code standards": "poetry run pflake8 .",
        "checking code vulnerabilities": "poetry run bandit -r kaskade/",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
