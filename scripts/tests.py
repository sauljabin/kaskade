import subprocess
import sys


def main():
    unittest = subprocess.run(["poetry", "run", "python", "-m", "unittest", "-v"])
    sys.exit(unittest.returncode)


if __name__ == "__main__":
    main()
