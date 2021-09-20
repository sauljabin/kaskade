import subprocess
import sys


def main():
    print(">>> coverage", flush=True)
    coverage = subprocess.run(
        [
            "poetry",
            "run",
            "coverage",
            "run",
            "-m",
            "unittest",
            "-v",
        ]
    )

    print(">>> coverage report", flush=True)
    coverage_report = subprocess.run(["poetry", "run", "coverage", "report", "-m"])

    print(">>> coverage html", flush=True)
    coverage_html = subprocess.run(["poetry", "run", "coverage", "html"])

    print(">>> coverage xml", flush=True)
    coverage_xml = subprocess.run(["poetry", "run", "coverage", "xml"])

    sys.exit(
        coverage.returncode
        or coverage_html.returncode
        or coverage_xml.returncode
        or coverage_report.returncode
    )


if __name__ == "__main__":
    main()
