from scripts import CommandProcessor


def main() -> None:
    commands = {
        "removing old packages": "rm -rf dist",
        "building the project": "poetry build",
        "creating docker image": "docker build -t sauljabin/kaskade:latest .",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
