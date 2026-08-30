import argparse
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def one_artifact(dist: Path, pattern: str) -> Path:
    artifacts = list(dist.glob(pattern))
    if len(artifacts) != 1:
        raise ValueError(f"expected one {pattern} artifact, found {len(artifacts)}")
    return artifacts[0]


def verify_wheel(wheel: Path, expected_version: str | None = None) -> str:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        version = metadata["Version"]

        if version is None:
            raise ValueError("wheel metadata does not contain a version")
        if expected_version is not None and version != expected_version:
            raise ValueError(f"wheel version is {version}, expected {expected_version}")
        if not wheel.name.startswith(f"kaskade-{version}-"):
            raise ValueError(f"wheel filename does not match metadata version {version}")
        if "kaskade/styles.css" not in names:
            raise ValueError("wheel does not contain kaskade/styles.css")
        if not any(name.endswith(".dist-info/entry_points.txt") for name in names):
            raise ValueError("wheel does not contain console entry points")

    return version


def verify_sdist(sdist: Path, version: str) -> None:
    if sdist.name != f"kaskade-{version}.tar.gz":
        raise ValueError(f"source distribution filename does not match wheel version {version}")
    expected_root = f"kaskade-{version}/"
    required = {"LICENSE", "pyproject.toml", "kaskade/styles.css"}
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())

    missing = {path for path in required if f"{expected_root}{path}" not in names}
    if missing:
        raise ValueError(f"source distribution is missing: {', '.join(sorted(missing))}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify release distribution metadata.")
    parser.add_argument("dist", type=Path)
    parser.add_argument("--expected-version")
    args = parser.parse_args()

    wheel = one_artifact(args.dist, "kaskade-*.whl")
    sdist = one_artifact(args.dist, "kaskade-*.tar.gz")
    version = verify_wheel(wheel, args.expected_version)
    verify_sdist(sdist, version)


if __name__ == "__main__":
    main()
