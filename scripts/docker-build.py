import subprocess
import sys


def main():
    commands = {
        # rm -rf dist
        "rm": ["rm", "-rf", "dist"],
        # poetry build
        "poetry": ["poetry", "build"],
        # docker build -t sauljabin/kaskade:latest -f ./docker/Dockerfile .
        "docker": [
            "docker",
            "build",
            "-t",
            "sauljabin/kaskade:latest",
            "-f",
            "./docker/Dockerfile",
            ".",
        ],
    }

    for name, command in commands.items():
        print(">>> ", name)
        result = subprocess.run(command)
        if result.returncode:
            sys.exit(result.returncode)

    sys.exit(0)


if __name__ == "__main__":
    main()
