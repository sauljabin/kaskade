# Development Instructions

### Setup

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# or on macOS
brew install uv
```

Create the project environment and install the locked development dependencies:

```bash
uv sync --locked
```

Run commands in that environment with `uv run`, for example:

```bash
uv run kaskade
```

The project is installed in editable mode, so source changes are available immediately.

Installing pre-commit hooks:

```bash
uv run pre-commit install
```

Running kaskade:

```bash
uv run kaskade
```

Run textual console:

```bash
uv run textual console --port 7342
uv run textual run --port 7342 --dev -c kaskade admin -b localhost:19092
uv run textual run --port 7342 --dev -c kaskade consumer -b localhost:19092 -t my-topic
```

### Scripts

Unit test modules live in `tests/unit`:

```bash
uv run python -m scripts.tests
```

E2E test modules live in `tests/e2e` and run against Confluent Kafka through
Testcontainers:

```bash
uv run python -m scripts.tests --e2e
```

Applying code styles:

```bash
uv run python -m scripts.styles
```

Running code analysis:

```bash
uv run python -m scripts.analyze
```

Generate banner:

```bash
uv run python -m scripts.banner
```

Generate admin and consumer screenshots with mock data (no Kafka broker required):

```bash
uv run python -m scripts.screenshots
```

### Build Artifacts

Build the Python wheel and source distribution:

```bash
uv build --clear
```

Both artifacts are written to `dist/`. Their version is derived from Git by
`hatch-vcs`: an exact `vMAJOR.MINOR.PATCH` tag produces a release version, while
an untagged commit produces a development version.

Verify that the artifacts contain matching versions and all required files:

```bash
uv run --locked python -m scripts.verify_release dist
```

The verification checks the wheel metadata, console entry point, packaged CSS,
required source-distribution files, and consistency between the wheel and source
distribution versions. Use `--expected-version VERSION` when the version must
also match a release tag.

### Docker

Build docker:

```bash
docker build -t sauljabin/kaskade:latest .
```

> Image tag `sauljabin/kaskade:latest`.

Run with docker (create a `config.yml` file):

```bash
docker run --rm -it --network sandbox sauljabin/kaskade:latest admin -b kafka1:9092
```

### Release

Git tags are the only source of release versions. Package metadata is derived from
the nearest semantic version tag by `hatch-vcs`; never edit a version field or a
changelog file for a release. GitHub Releases are the canonical release history.

Before releasing, ensure `main` is current, clean, and passing CI:

```bash
git switch main
git pull --ff-only origin main
git status --short
uv lock --check
uv run --locked python -m scripts.analyze
uv run --locked python -m scripts.tests
```

Choose the next version according to [Semantic Versioning](https://semver.org/),
then create and push an annotated tag:

```bash
git tag -a v4.1.0 -m "Release v4.1.0"
git push origin v4.1.0
```

The release workflow validates that the tag is exactly `vMAJOR.MINOR.PATCH` and
points to a commit on `main`. It then tests and builds the distributions, derives
release notes from Conventional Commits, and waits for approval in the protected
`release` environment. After approval, PyPI and Docker Hub are published before
the GitHub release is created.

The GitHub `release` environment must contain `DOCKER_HUB_USERNAME` and
`DOCKER_HUB_ACCESS_TOKEN`. Configure the PyPI trusted publisher for owner
`sauljabin`, repository `kaskade`, workflow `release.yml`, and environment
`release`. GitHub release creation uses the built-in token and needs no personal
access token.

If publishing fails, do not move the tag or create a replacement version commit.
Fix the external configuration if necessary and rerun only the failed GitHub
Actions jobs. PyPI artifacts are immutable; if an incorrect artifact was already
published, create a new patch version instead of reusing the tag.

### Manual Tests

The standalone `sandbox` package owns its Compose environment, population tools,
and Avro, JSON Schema, and Protobuf models. These models are intentionally
separate from the fixtures under `tests/unit`.

Start the sandbox's three-node Confluent Kafka cluster, Apicurio Registry, and
Confluent Schema Registry:

```bash
docker compose --project-directory sandbox up -d
```

Stop sandbox:

```bash
docker compose --project-directory sandbox down -v
```

Kafka is available at `localhost:19092`, `localhost:29092`, and
`localhost:39092`. Confluent Schema Registry is available at
`http://localhost:18081`; Apicurio's compatibility API is available at
`http://localhost:18082/apis/ccompat/v7`. Image versions and the Kafka cluster
ID are defined in `sandbox/.env`.

Populate Kafka using Confluent Schema Registry:

```bash
uv run python -m sandbox
```

To use Apicurio instead, populate a fresh sandbox with its compatibility API:

```bash
uv run python -m sandbox --registry http://localhost:18082/apis/ccompat/v7
```

Read help messages:

```bash
uv run kaskade admin --help
uv run kaskade consumer --help
```

Test admin:

```bash
uv run kaskade admin -b localhost:19092
```

Test consumer without deserialization:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t string
```

Test consumer with nulls:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v string -t null
```

Test consumer with deserializers:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v string -t string
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v integer -t integer
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v long -t long
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v float -t float
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v double -t double
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v boolean -t boolean
```

Test json consumer with Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t json-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test json consumer without Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v json -t json
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -k string -v json -t json-schema
```

Test avro consumer with Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t avro-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test avro consumer with Apicurio Registry:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t avro-schema \
        -k string -v registry \
        --registry url=http://localhost:18082/apis/ccompat/v7
```

Test avro consumer without Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t avro \
        -k string -v avro \
        --avro value=sandbox/avro_model/user.avsc
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t avro-schema \
        -k string -v avro \
        --avro value=sandbox/avro_model/user.avsc \
        --avro framing=confluent
```

Test protobuf consumer:

The checked-in descriptor is generated from `sandbox/protobuf_model/user.proto`.
After changing the schema, regenerate the sandbox artifacts with `protoc`:

```bash
protoc --include_imports \
       --proto_path=sandbox/protobuf_model \
       --python_out=sandbox/protobuf_model \
       --pyi_out=sandbox/protobuf_model \
       --descriptor_set_out=sandbox/protobuf_model/user.desc \
       sandbox/protobuf_model/user.proto
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t protobuf \
        -k string -v protobuf \
        --protobuf descriptor=sandbox/protobuf_model/user.desc \
        --protobuf value=User
```

```bash
uv run kaskade consumer -b localhost:19092 --from-beginning -t protobuf-schema \
        -k string -v protobuf \
        --protobuf descriptor=sandbox/protobuf_model/user.desc \
        --protobuf value=User
```
