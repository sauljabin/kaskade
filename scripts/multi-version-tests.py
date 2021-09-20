import subprocess
import sys


def main():
    tox = subprocess.run(["poetry", "run", "tox", "-q"])
    sys.exit(tox.returncode)


if __name__ == "__main__":
    main()
