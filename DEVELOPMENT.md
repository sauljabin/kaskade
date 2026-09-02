# Development Instructions

## Setup

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

## Scripts

Unit test modules live in `tests/unit`:

```bash
uv run --locked python -m scripts.tests
```

E2E test modules live in `tests/e2e` and run against disposable Confluent Kafka
and Schema Registry containers through Testcontainers. Docker must be running;
the first run may pull the required images. Registry coverage creates separate
JSON Schema, Avro, and Protobuf topics and consumes each through the Registry
deserializer, then consumes the same records through the corresponding local
deserializers with `framing=confluent`:

```bash
uv run --locked python -m scripts.tests --e2e
```

Applying code styles:

```bash
uv run python -m scripts.styles
```

Running code analysis:

```bash
uv run --locked python -m scripts.analyze
```

Generate banner:

```bash
uv run python -m scripts.banner
```

Generate admin and consumer screenshots with mock data (no Kafka broker required):

```bash
uv run python -m scripts.screenshots
```

## Build Artifacts

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

## Docker

Build the Docker image:

```bash
docker build -t sauljabin/kaskade:latest .
```

Run the image on the sandbox network:

```bash
docker run --rm -it --network sandbox sauljabin/kaskade:latest admin -b kafka1:9092
```

## Release

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

## Manual Tests

The standalone `sandbox` package owns its Compose environment, population tools,
and inline Avro, JSON Schema, and Protobuf model definitions. These definitions
are intentionally separate from the variables used by the automated tests.

Use this sequence for a complete manual test:

1. Start the local services.
2. Populate all topics or a selected subset.
3. Inspect registry data when testing schema-backed topics.
4. Run the Admin and Consumer smoke tests.
5. Stop the services and remove their volumes.

### Start the local sandbox

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

### Populate test topics

The default command creates and populates every available sandbox topic. It
registers separate Avro, JSON Schema, and Protobuf fixtures in both Confluent
Schema Registry and the native Apicurio Core Registry API:

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

Override either registry URL when the sandbox services are hosted elsewhere:

```bash
uv run python -m sandbox \
    --registry http://localhost:18081 \
    --apicurio-registry http://localhost:18082/apis/registry/v3
```

### Inspect registry APIs with HTTPie

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

### Populate a remote Amazon MSK cluster

To populate an Amazon MSK cluster that uses IAM authentication, run the tool from
a network with access to the brokers and pass the IAM bootstrap servers and AWS
region. AWS credentials use the standard provider chain:

```bash
uv run python -m sandbox \
    --bootstrap-servers "${AWS_MSK_BOOTSTRAP_SERVERS}" \
    --aws region=us-east-1
```

The Schema Registry URL remains independently configurable with `--registry`.

The IAM principal used for population needs `Connect`, `CreateTopic`,
`DescribeTopic`, and `WriteData`. Replace the placeholders and narrow the topic
wildcard when appropriate:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectToCluster",
      "Effect": "Allow",
      "Action": "kafka-cluster:Connect",
      "Resource": "arn:aws:kafka:<region>:<account-id>:cluster/<cluster-name>/<cluster-uuid>"
    },
    {
      "Sid": "CreateAndPopulateTopics",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:CreateTopic",
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData"
      ],
      "Resource": "arn:aws:kafka:<region>:<account-id>:topic/<cluster-name>/<cluster-uuid>/*"
    }
  ]
}
```

For a SASL/SCRAM or mTLS cluster, grant the population principal access to the
test topics. Run this as an ACL administrator and configure
`admin-client.properties` for that administrator:

```bash
kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Create \
    --operation Write \
    --operation Describe \
    --topic '*'
```

### Run application smoke tests

Confirm both command interfaces render successfully:

```bash
uv run kaskade admin --help
uv run kaskade consumer --help
```

Open the Admin application and verify the populated topics and their metadata:

```bash
uv run kaskade admin -b localhost:19092
```

#### Primitive and JSON consumers

Start with raw bytes:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t string
```

Every record in the `null` topic has a null key, value, and `sandbox-null`
header:

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

Test raw and Confluent-framed payloads with the local JSON deserializer:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -k string -v json -t json
uv run kaskade consumer -b localhost:19092 --earliest -k string -v json -t json-schema \
        --json framing=confluent
```

#### Schema Registry consumers

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
        --fallback encoding=hex \
        --registry url=http://localhost:18081
```

The `errors` topic cycles through a malformed key, malformed value, both fields
malformed, an invalid UTF-8 header, and a fully valid record. Malformed fields
contain randomized bytes, and `sandbox-error-case` identifies each case.

Test an Avro payload through Confluent Schema Registry:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t avro-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test a Protobuf payload through Confluent Schema Registry without a local
descriptor:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t protobuf-schema \
        -k string -v registry \
        --registry url=http://localhost:18081
```

Test the native Apicurio Avro payload:

```bash
uv run kaskade consumer -b localhost:19092 --earliest -t avro-schema-apicurio \
        -k string -v registry \
        --registry provider=APICURIO \
        --registry apicurio.registry.url=http://localhost:18082/apis/registry/v3
```

Use `json-schema-apicurio` or `protobuf-schema-apicurio` to exercise the other
native formats with the same registry configuration. Apicurio's ccompat endpoint
remains available through the default Confluent provider and `--registry url=...`.

#### Local-schema consumers

Sandbox schemas and models are defined inline, so the repository does not carry
local Avro schema or Protobuf descriptor files. To exercise the local `avro` or
`protobuf` deserializers, provide your own `.avsc` or descriptor-set file using
the commands documented in `USAGE.md`.

### Stop the local sandbox

Remove the containers, networks, and persisted test data when manual testing is
complete:

```bash
docker compose --project-directory sandbox down -v
```
