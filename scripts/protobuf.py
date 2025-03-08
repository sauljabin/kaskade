from scripts import CommandProcessor


def main() -> None:
    path = "tests/protobuf_model"
    commands = {
        "build protobuf examples": (
            f"protoc --include_imports --proto_path={path} --python_out={path} --pyi_out={path} --descriptor_set_out={path}/user.desc {path}/user.proto"
        ),
    }
    command_processor = CommandProcessor(commands)
    command_processor.run()


if __name__ == "__main__":
    main()
