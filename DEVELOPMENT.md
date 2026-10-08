# Development

## Contents

- [Setup](#setup)
- [Scripts](#scripts)
- [Configuration conventions](#configuration-conventions)
- [Website](#website)
- [Build Artifacts](#build-artifacts)
- [Release](#release)
- [Sandbox](#sandbox)
  - [Start the local sandbox](#start-the-local-sandbox)
  - [Populate test topics](#populate-test-topics)
  - [Inspect registry APIs with HTTPie](#inspect-registry-apis-with-httpie)
  - [Populate a remote Amazon MSK cluster](#populate-a-remote-amazon-msk-cluster)
  - [Stop the local sandbox](#stop-the-local-sandbox)

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

Commits run formatting, screenshot generation, and code analysis. Pushes run the
unit tests and the E2E tests, which require Docker. A push, pull request, or
`main` commit that changes only documentation, the site, images, examples, or
GitHub templates skips E2E, both in the hook and in CI. A manual run of the CI
workflow from the Actions tab always runs E2E.

Running kaskade:

```bash
uv run kaskade
```

Run textual console:

```bash
uv run textual console --port 7342
uv run textual run --port 7342 --dev -c kaskade admin -b localhost:9092
uv run textual run --port 7342 --dev -c kaskade consumer -b localhost:9092 -t my-topic
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
deserializers with `framing=confluent` or `framing=apicurio`:

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

Generate the framed README banner and borderless site variant:

```bash
uv run python -m scripts.banner
```

Generate framed README screenshots and borderless site variants with mock data
(no Kafka broker required):

```bash
uv run python -m scripts.screenshots
```

## Configuration conventions

Each setting belongs to the file that owns its responsibility:

- `--config-file` (INI) says how to connect to a cluster: `[kafka]`,
  `[registry]`, and `[aws]`.
- `settings.yaml` says how Kaskade behaves: theme, custom themes, keymap, admin
  auto-refresh, and operation timeouts. Command-line options such as `--theme`,
  `--refresh-interval`, and `--timeout` override it for one session. The CLI
  loads `settings.yaml` once, applies those overrides, and passes the resulting
  `AppSettings` to the application.

Name new settings the same way:

- In `settings.yaml`, use nesting for hierarchy and kebab-case for multi-word
  keys, such as `admin: refresh-interval:`. Don't put dots in YAML keys;
  `refresh.interval:` is a literal key, not `refresh: interval:`.
- Use dots only in flat names where nesting isn't possible: Kafka and Registry
  properties in the INI and `--kafka`/`--registry`, `--timeout` properties such
  as `admin.write`, and Textual binding IDs in `keymap`, such as
  `kaskade.records.chunk-size`.

## Website

The static landing page lives in `site/`. Assemble a local preview with the same
generated assets used by GitHub Pages:

```bash
mkdir -p /tmp/kaskade-site-preview/assets
cp -R site/. /tmp/kaskade-site-preview/
cp images/banner-borderless.svg \
   images/admin-borderless.svg \
   images/consumer-borderless.svg \
   images/littlehorse-badge.svg \
   images/textual-badge.svg \
   /tmp/kaskade-site-preview/assets/
uv run python -m http.server 8000 --directory /tmp/kaskade-site-preview
```

Open `http://localhost:8000/`. The Pages workflow assembles and uploads the same
artifact for pull requests, but deploys only from `main`. The repository's Pages
publishing source must be **GitHub Actions**.

The social preview (`og:image`, 1280×640) is `site/social-preview.png`, rendered
from `images/social-preview.svg` with headless Chrome or Chromium. The same
image is the repository's social preview, uploaded under Settings > General >
Social preview; GitHub has no API for it. After editing the SVG, render it on
macOS or Linux:

```bash
chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"  # Linux: chromium
"$chrome" --headless=new --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=1280,640 --screenshot="$PWD/site/social-preview.png" \
  "file://$PWD/images/social-preview.svg"
```

The PNG uses the rendering machine's monospace font, so check it before
committing.

## Build Artifacts

Build the Python wheel and source distribution:

```bash
uv build --clear
```

Both artifacts are written to `dist/`. Their version is derived from Git by
`hatch-vcs`: an exact `vMAJOR.MINOR.PATCH` tag, optionally suffixed with PEP 440
`aN`, `bN`, or `rcN`, produces a release version, while an untagged commit
produces a development version.

Verify that the artifacts contain matching versions and all required files:

```bash
uv run --locked python -m scripts.verify_release dist
```

The verification checks the wheel metadata, console entry point, packaged CSS,
required source-distribution files, and consistency between the wheel and source
distribution versions. Use `--expected-version VERSION` when the version must
also match a release tag.

## Release

Follow the [AI Agent Release Checklist](RELEASE_CHECKLIST.md) for shared checks,
major, minor, or patch reviews, post-release verification, and announcement
approval. This section owns the publishing commands and recovery procedure.

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

For a prerelease, append the next PEP 440 `aN`, `bN`, or `rcN` suffix to
`release_version`. The release workflow validates the stable or prerelease tag
and requires it to point to a commit on `main`. It then tests and builds the
distributions, derives release notes from Conventional Commits, and waits for
approval in the protected `release` environment. After approval, PyPI is
published before the GitHub release is created.

Configure the PyPI trusted publisher for owner
`sauljabin`, repository `kaskade`, workflow `release.yml`, and environment
`release`. GitHub release creation uses the built-in token and needs no personal
access token.

If publishing fails, do not move the tag or create a replacement version commit.
Fix the external configuration if necessary and rerun only the failed GitHub
Actions jobs. PyPI artifacts are immutable; if an incorrect artifact was already
published, create a new patch version instead of reusing the tag.

## Sandbox

The standalone `sandbox` package owns its Compose environment, population tools,
and inline Avro, JSON Schema, and Protobuf model definitions. Those fixtures stay
separate from the automated tests, while `sandbox/.env` provides their shared
container image versions. The release smoke tests in
[MANUAL_TESTING.md](MANUAL_TESTING.md) run against it.

### Start the local sandbox

Start the single-node Confluent Kafka cluster, Confluent Schema Registry, and
Apicurio Registry:

```bash
docker compose --project-directory sandbox up -d
```

The sandbox exposes:

| Service | Address |
| --- | --- |
| Kafka broker | `localhost:9092` |
| Confluent Schema Registry | `http://localhost:8081` |
| Apicurio Confluent-compatible API | `http://localhost:8082/apis/ccompat/v7` |
| Apicurio Core Registry API | `http://localhost:8082/apis/registry/v3` |

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
    --replication-factor 1 \
    --min-insync-replicas 1
```

Override either registry URL when the sandbox services are hosted elsewhere:

```bash
uv run python -m sandbox \
    --registry http://localhost:8081 \
    --apicurio-registry http://localhost:8082/apis/registry/v3
```

### Inspect registry APIs with HTTPie

After populating the sandbox, use [HTTPie](https://httpie.io/) to inspect the
registered subjects and schemas.

Query Confluent Schema Registry:

```bash
http GET http://localhost:8081/subjects
http GET http://localhost:8081/subjects/avro-schema-value/versions
http GET http://localhost:8081/subjects/avro-schema-value/versions/latest
http GET http://localhost:8081/config
```

Query Apicurio's Confluent-compatible API:

```bash
http GET http://localhost:8082/apis/ccompat/v7/subjects
http GET http://localhost:8082/apis/ccompat/v7/subjects/avro-schema-value/versions
http GET http://localhost:8082/apis/ccompat/v7/subjects/avro-schema-value/versions/latest
http GET http://localhost:8082/apis/ccompat/v7/config
```

Query Apicurio's native Core Registry API:

```bash
http GET http://localhost:8082/apis/registry/v3/search/artifacts
http GET http://localhost:8082/apis/registry/v3/search/versions
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
    --bootstrap-server "${AWS_MSK_BOOTSTRAP_SERVERS}" \
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

### Stop the local sandbox

Remove the containers, networks, and persisted test data when you're done:

```bash
docker compose --project-directory sandbox down -v
```
