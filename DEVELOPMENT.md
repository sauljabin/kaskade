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

### Kafka Cluster

Run local cluster:

```bash
docker compose up -d
```

### Docker

Build docker:

```bash
python -m scripts.docker
```

> Image tag `sauljabin/kaskade:latest`.

Run with docker (create a `config.yml` file):

```bash
docker run --rm -it --network cluster sauljabin/kaskade:latest admin -b kafka1:9092
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

Clone the kafka sandbox:

```bash
git clone https://github.com/sauljabin/kafka-sandbox.git
```

> Run all the examples at [Kafka Sandbox](https://sauljabin.github.io/kafka-sandbox/introduction.html).

Test admin:

```bash
kaskade admin -b localhost:19092
```

Test consumer natives:

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -t client.string
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v string -t client.string
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v integer -t client.integer
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v long -t client.long
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v float -t client.float
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v double -t client.double
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v boolean -t client.boolean
```

Test consumer json:

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v json -t client.users
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v json -t client.schema.users
```

Test consumer avro:

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v avro -t client.suppliers \
        -s url=http://localhost:8081
```

Test consumer protobuf:

> Install `protoc` with `brew install protobuf`

```bash
protoc --include_imports --descriptor_set_out=my-descriptor.desc \
       --proto_path="${KAFKA_SANDBOX_PATH}/kafka-protobuf/src/main/proto/" \
       "${KAFKA_SANDBOX_PATH}/kafka-protobuf/src/main/proto/Invoice.proto"
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v protobuf -t client.invoices \
        -p descriptor=my-descriptor.desc -p value=Invoice
```

```bash
kaskade consumer -b localhost:19092 -x auto.offset.reset=earliest \
        -k string -v protobuf -t client.schema.invoices \
        -p descriptor=my-descriptor.desc -p value=Invoice
```