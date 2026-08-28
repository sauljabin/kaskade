from scripts import CommandProcessor


def main() -> None:
    commands = {
        "building the project": "uv build --clear",
        "creating docker image": "docker build -t sauljabin/kaskade:latest .",
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
