# Development Instructions

Installing poetry:

```shell
pipx install poetry
```

Installing development dependencies:

```shell
poetry install
```

Open a terminal within the project's virtual environment:

```shell
poetry shell
```

> See more at https://python-poetry.org/docs/cli#shell.

Installing pre-commit hooks:

```shell
pre-commit install
```

Running kaskade:

```shell
kaskade
```

Run textual console:

```shell
textual console --port 7342
textual run --port 7342 --dev -c kaskade -b localhost:19092
```

### Scripts

Running unit tests:

```shell
python -m scripts.tests
```

Applying code styles:

```shell
python -m scripts.styles
```

Running code analysis:

```shell
python -m scripts.analyze
```

Running banner:

```shell
python -m scripts.banner
```
### Kafka Cluster

Run local cluster:

```shell
docker compose up -d
```

### Docker

Build docker:

```shell
python -m scripts.docker
```

> Image tag `sauljabin/kaskade:latest`.

Run with docker (create a `config.yml` file):

```shell
docker run --rm -it --network cluster sauljabin/kaskade:latest -b kafka1:9092
```

### Release

Help:

```shell
python -m scripts.bump --help
```

Upgrade (`major.minor.patch`):

```shell
python -m scripts.bump patch
```

> More info at https://python-poetry.org/docs/cli/#version and https://semver.org/.
> For changelog management check https://github.com/sauljabin/changeloggh.