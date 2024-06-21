# Development Instructions

Installing poetry:

```shell
pipx install poetry
```

Installing development dependencies:

```shell
poetry install
```

Installing pre-commit hooks:

```shell
poetry run pre-commit install
```

Running kaskade:

```shell
poetry run kaskade
```

Run textual console:

```shell
poetry run textual console --port 7342
poetry run textual run --port 7342 --dev -c kaskade -b localhost:19092
```

### Scripts

Running unit tests:

```shell
poetry run python -m scripts.tests
```

Applying code styles:

```shell
poetry run python -m scripts.styles
```

Running code analysis:

```shell
poetry run python -m scripts.analyze
```

Running code coverage:

```shell
poetry run python -m scripts.coverage
```

### Kafka Cluster

Run local cluster:

```shell
docker compose up -d
```

### Docker

Build docker:

```shell
poetry run python -m scripts.docker
```

> Image tag `sauljabin/kaskade:latest`.

Run with docker (create a `config.yml` file):

```shell
docker run --rm -it --network cluster sauljabin/kaskade:latest -b kafka1:9092
```

### Release

Help:

```shell
poetry run python -m scripts.bump --help
```

Upgrade (`major.minor.patch`):

```shell
poetry run python -m scripts.bump patch
```

> More info at https://python-poetry.org/docs/cli/#version and https://semver.org/.
> For changelog management check https://github.com/sauljabin/changeloggh.