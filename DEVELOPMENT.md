# Development Instructions

### Setup

Installing poetry:

```bash
pipx install poetry
```

Installing development dependencies:

```bash
poetry install
```

Open a terminal within the project's virtual environment:

```bash
poetry shell
```

> See more at https://python-poetry.org/docs/cli#shell.

Installing pre-commit hooks:

```bash
pre-commit install
```

Running kaskade:

```bash
kaskade
```

Run textual console:

```bash
textual console --port 7342
textual run --port 7342 --dev -c kaskade admin -b localhost:19092
textual run --port 7342 --dev -c kaskade consumer -b localhost:19092 -t my-topic
```

### Scripts

Unit tests:

```bash
python -m scripts.tests
```

Applying code styles:

```bash
python -m scripts.styles
```

Running code analysis:

```bash
python -m scripts.analyze
```

Generate banner:

```bash
python -m scripts.banner
```

### Docker

Build docker:

```bash
python -m scripts.docker
```

> Image tag `sauljabin/kaskade:latest`.

Run with docker (create a `config.yml` file):

```bash
docker run --rm -it --network sandbox sauljabin/kaskade:latest admin -b kafka1:9092
```

### Release

Help:

```bash
python -m scripts.bump --help
```

Upgrade (`major.minor.patch`):

```bash
python -m scripts.bump patch
```

> More info at https://python-poetry.org/docs/cli/#version and https://semver.org/.
> For changelog management check https://github.com/sauljabin/changeloggh.

### Manual Tests

Run local sandbox:

```bash
docker compose -f docker-compose.confluent.yml up -d
docker compose -f docker-compose.redpanda.yml up -d
```

Stop sandbox:

```bash
docker compose -f docker-compose.confluent.yml down -v
docker compose -f docker-compose.redpanda.yml down -v
```

> Use the docker-compose file you need.

Populate kafka:

```bash
python -m scripts.sandbox
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

```bash
kaskade consumer -b localhost:19092 --from-beginning -k string -v json -t json
```

Test consumer with Schema Registry:

```bash
kaskade consumer -b localhost:19092 --from-beginning -s url=http://localhost:8081 -t schemas.json
```

```bash
kaskade consumer -b localhost:19092 --from-beginning -s url=http://localhost:8081 -t schemas.avro
```

Test consumer protobuf:

> Install `protoc` with `brew install protobuf`

If there is a change in the protobuf files generate the classes with:

```bash
python -m scripts.protobuf
```

```bash
kaskade consumer -b localhost:19092 --from-beginning \
        -k string -v protobuf -t invoices \
        -p descriptor=my-descriptor.desc -p value=Invoice
```

```bash
kaskade consumer -b localhost:19092 --from-beginning \
        -k string -v protobuf -t schema.invoices \
        -p descriptor=my-descriptor.desc -p value=Invoice
```
