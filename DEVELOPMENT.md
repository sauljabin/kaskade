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
release_version="MAJOR.MINOR.PATCH"
git tag -a "v${release_version}" -m "Release v${release_version}"
git push origin "v${release_version}"
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

Use this sequence for a complete manual test:

1. Start the local services.
2. Populate all topics or a selected subset.
3. Inspect registry data when testing schema-backed topics.
4. Run the Admin and Consumer smoke tests.
5. Stop the services and remove their volumes.

#### Start the local sandbox

Start the three-node Confluent Kafka cluster, Confluent Schema Registry, and
Apicurio Registry:

```bash
docker compose --project-directory sandbox up -d
```

The sandbox exposes:

| Service | Address |
| --- | --- |
| Kafka brokers | `localhost:19092`, `localhost:29092`, `localhost:39092` |
| Confluent Schema Registry | `http://localhost:18081` |
| Apicurio Confluent-compatible API | `http://localhost:18082/apis/ccompat/v7` |
| Apicurio Core Registry API | `http://localhost:18082/apis/registry/v3` |

Image versions and the Kafka cluster ID are defined in `sandbox/.env`.

#### Populate test topics

The default command creates and populates every available sandbox topic using
Confluent Schema Registry:

```bash
uv run python -m sandbox
```

Repeat `--topic` to populate only a subset. The accepted topic names are listed
by `uv run python -m sandbox --help`:

```bash
uv run python -m sandbox --topic string --topic errors
```

Topic creation uses 10 partitions and the broker defaults for replication
factor and minimum in-sync replicas. Override them when testing a specific
topology:

```bash
uv run python -m sandbox \
    --partitions 6 \
    --replication-factor 3 \
    --min-insync-replicas 2
```

To test Apicurio, start from an empty sandbox and populate it through the
Confluent-compatible API:

```bash
uv run python -m sandbox --registry http://localhost:18082/apis/ccompat/v7
```

#### Inspect registry APIs with HTTPie

After populating the sandbox, use [HTTPie](https://httpie.io/) to inspect the
registered subjects and schemas.

Query Confluent Schema Registry:

```bash
http GET http://localhost:18081/subjects
http GET http://localhost:18081/subjects/avro-schema-value/versions
http GET http://localhost:18081/subjects/avro-schema-value/versions/latest
http GET http://localhost:18081/config
```

Query Apicurio's Confluent-compatible API:

```bash
http GET http://localhost:18082/apis/ccompat/v7/subjects
http GET http://localhost:18082/apis/ccompat/v7/subjects/avro-schema-value/versions
http GET http://localhost:18082/apis/ccompat/v7/subjects/avro-schema-value/versions/latest
http GET http://localhost:18082/apis/ccompat/v7/config
```

Query Apicurio's native Core Registry API:

```bash
http GET http://localhost:18082/apis/registry/v3/search/artifacts
http GET http://localhost:18082/apis/registry/v3/search/versions
```

The `avro-schema-value` subject exists after populating the `avro-schema` topic.
Substitute another name returned by the `/subjects` request when testing a
different schema-backed topic.

#### Populate a remote Amazon MSK cluster

To populate an Amazon MSK cluster that uses IAM authentication, run the tool from
a network with access to the brokers and pass the IAM bootstrap servers and AWS
region. AWS credentials use the standard provider chain:

```bash
uv run python -m sandbox \
    --bootstrap-servers "${AWS_MSK_BOOTSTRAP_SERVERS}" \
    --aws region=us-east-1
```

The Schema Registry URL remains independently configurable with `--registry`.
See the sandbox requirements under [IAM permissions](USAGE.md#iam-permissions)
or [Kafka ACLs](USAGE.md#kafka-acls).

#### Run application smoke tests

Confirm both command interfaces render successfully:

```bash
uv run kaskade admin --help
uv run kaskade consumer --help
```

Open the Admin application and verify the populated topics and their metadata:

```bash
uv run kaskade admin -b localhost:19092
```

##### Primitive and JSON consumers

Start with raw bytes:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t string
```

Test null keys and values. Every record in the `null` topic has both fields set
to Kafka null:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -k string -v string -t null
```

Test every primitive deserializer:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -k string -v string -t string
uv run kaskade consumer -b localhost:19092 --earliest -k string -v integer -t integer
uv run kaskade consumer -b localhost:19092 --earliest -k string -v long -t long
uv run kaskade consumer -b localhost:19092 --earliest -k string -v float -t float
uv run kaskade consumer -b localhost:19092 --earliest -k string -v double -t double
uv run kaskade consumer -b localhost:19092 --earliest -k string -v boolean -t boolean
```

Test JSON payloads without Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -k string -v json -t json
uv run kaskade consumer -b localhost:19092 --earliest -k string -v json -t json-schema
```

##### Schema Registry consumers

Test a JSON Schema payload through Confluent Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t json-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test independent key and value deserialization fallbacks:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t errors \
        -k registry -v registry \
        --registry url=http://localhost:18081
```

The `errors` topic cycles through a malformed key, malformed value, both fields
malformed, and a fully valid record. Malformed fields contain randomized bytes,
and the `sandbox-error-case` header identifies each case.

Test an Avro payload through Confluent Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t avro-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test the same Avro payload through Apicurio after populating that registry:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t avro-schema \
        -k string -v registry \
        --registry url=http://localhost:18082/apis/ccompat/v7
```

##### Local-schema consumers

Test raw and Confluent-framed Avro payloads with a local schema:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t avro \
        -k string -v avro \
        --avro value=sandbox/avro_model/user.avsc

uv run kaskade consumer -b localhost:19092 --earliest -t avro-schema \
        -k string -v avro \
        --avro value=sandbox/avro_model/user.avsc \
        --avro framing=confluent
```

Test raw and Confluent-framed Protobuf payloads with the checked-in descriptor:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t protobuf \
        -k string -v protobuf \
        --protobuf descriptor=sandbox/protobuf_model/user.desc \
        --protobuf value=User

uv run kaskade consumer -b localhost:19092 --earliest -t protobuf-schema \
        -k string -v protobuf \
        --protobuf descriptor=sandbox/protobuf_model/user.desc \
        --protobuf value=User
```

The descriptor is generated from `sandbox/protobuf_model/user.proto`. After
changing the schema, regenerate the sandbox artifacts with `protoc`:

```bash
protoc --include_imports \
       --proto_path=sandbox/protobuf_model \
       --python_out=sandbox/protobuf_model \
       --pyi_out=sandbox/protobuf_model \
       --descriptor_set_out=sandbox/protobuf_model/user.desc \
       sandbox/protobuf_model/user.proto
```

#### Stop the local sandbox

Remove the containers, networks, and persisted test data when manual testing is
complete:

```bash
docker compose --project-directory sandbox down -v
```
