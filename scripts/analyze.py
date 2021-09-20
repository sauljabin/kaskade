import subprocess
import sys


def main():
    print(">>> black", flush=True)
    black = subprocess.run(["poetry", "run", "black", "--check", "."])

    print(">>> isort", flush=True)
    isort = subprocess.run(["poetry", "run", "isort", "--check", "."])

    print(">>> flake8", flush=True)
    flake8 = subprocess.run(["poetry", "run", "pflake8", "."])

    print(">>> bandit", flush=True)
    bandit = subprocess.run(["poetry", "run", "bandit", "-r", "kaskade/"])

    sys.exit(
        black.returncode or isort.returncode or flake8.returncode or bandit.returncode
    )


if __name__ == "__main__":
    main()
