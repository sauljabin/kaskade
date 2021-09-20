import subprocess
import sys


def main():
    print(">>> black")
    black = subprocess.run(["poetry", "run", "black", "."])

    print(">>> isort")
    isort = subprocess.run(["poetry", "run", "isort", "."])

    sys.exit(black.returncode or isort.returncode)


if __name__ == "__main__":
    main()
