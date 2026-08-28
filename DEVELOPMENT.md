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

Unit tests:

```bash
uv run python -m scripts.tests
```

E2E tests:

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

### Docker

Build docker:

```bash
uv run python -m scripts.docker
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

Run local sandbox (chose one of `confluent`, `redpanda` or `apicurio`):

```bash
docker compose -f docker-compose.confluent.yml up -d
docker compose -f docker-compose.redpanda.yml up -d
docker compose -f docker-compose.apicurio.yml up -d
```

Stop sandbox:

```bash
docker compose -f docker-compose.confluent.yml down -v
docker compose -f docker-compose.redpanda.yml down -v
docker compose -f docker-compose.apicurio.yml down -v
```

> Use the docker-compose file you need.

Populate kafka:

```bash
python -m scripts.sandbox
```

Read help messages:

```bash
kaskade admin --help
kaskade consumer --help
```

Test admin:

```bash
kaskade admin -b localhost:19092
```

Test consumer without deserialization:

```bash
kaskade consumer -b localhost:19092 --from-beginning -t string
```

Test consumer with nulls:

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v string -t null
```

Test consumer with deserializers:

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v string -t string
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v integer -t integer
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v long -t long
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v float -t float
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v double -t double
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v boolean -t boolean
```

Test json consumer with Schema Registry (Confluent and Redpanda):

```bash
kaskade consumer -b localhost:19092 --from-beginning -t json-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test json consumer without Schema Registry:

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v json -t json
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v json -t json-schema
```

Test avro consumer with Schema Registry (Confluent and Redpanda):

```bash
kaskade consumer -b localhost:19092 --from-beginning -t avro-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test avro consumer with Apicurio Registry:

```bash
kaskade consumer -b localhost:19092 --from-beginning -t avro-schema \
        -k string -v registry \
        --registry url=http://localhost:18081/apis/ccompat/v7
```

Test avro consumer without Schema Registry:

```bash
kaskade consumer -b localhost:19092 --from-beginning -t avro \
        -k string -v avro \
        --avro value=tests/avro_model/user.avsc
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -t avro-schema \
        -k string -v avro \
        --avro value=tests/avro_model/user.avsc
```

Test protobuf consumer:

> Install `protoc` with `brew install protobuf`.\
> Update descriptor with `python -m scripts.protobuf`.

```bash
kaskade consumer -b localhost:19092 --from-beginning -t protobuf \
        -k string -v protobuf \
        --protobuf descriptor=tests/protobuf_model/user.desc \
        --protobuf value=User
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -t protobuf-schema \
        -k string -v protobuf \
        --protobuf descriptor=tests/protobuf_model/user.desc \
        --protobuf value=User
```
