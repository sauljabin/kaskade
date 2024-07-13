<p align="center">
  <a href="https://github.com/sauljabin/kaskade">
    <img alt="kaskade" width="400" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/banner.png">
  </a>
</p>

<a href="https://github.com/sauljabin/kaskade">
  <img alt="GitHub" src="https://img.shields.io/badge/github-blueviolet?logo=github&logoColor=white">
</a>
<a href="https://hub.docker.com/r/sauljabin/kaskade">
  <img alt="DockerHub" src="https://img.shields.io/badge/docker-blue?logo=docker&logoColor=white">
</a>
<a href="https://github.com/sponsors/sauljabin">
  <img alt="donate" src="https://img.shields.io/badge/donate-EA4AAA?logo=github-sponsors&logoColor=white">
</a>
<a href="https://libraries.io/pypi/kaskade">
  <img alt="Libraries.io dependency status for latest release" src="https://img.shields.io/librariesio/release/pypi/kaskade?label=">
</a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE">
  <img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade">
</a>
<a href="https://pypi.org/project/kaskade">
  <img alt="Version" src="https://img.shields.io/pypi/v/kaskade?label=latest">
</a>
<a href="https://pypi.org/project/kaskade">
  <img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade?label=python">
</a>
<a href="https://pypi.org/project/kaskade">
  <img alt="Platform" src="https://img.shields.io/badge/os-linux%20%7C%20macos-blue">
</a>

## Kaskade

Kaskade is a text user interface (TUI) for Apache Kafka, built with [Textual](https://github.com/Textualize/textual)
by [Textualize](https://www.textualize.io/). It includes features like:

- Admin:
    - List topics, partitions, groups and group members.
    - Topic information like lag, replicas and records count.
    - Create, edit and delete topics.
    - Filter topics by name.
- Consumer:
    - Json, string, integer, long, float, boolean and double deserialization.
    - Filter by key, value, header and/or partition.
    - Schema Registry support with avro.

## Screenshots

<table>
  <tr>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/admin.png">
    </td>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/create-topic.png">
    </td>
  </tr>
  <tr>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/consumer.png">
    </td>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/record.png">
    </td>
  </tr>
</table>

## Installation

These will install `kaskade` and `kskd` aliases.

#### Install it with `brew`:

```bash
brew install kaskade
```

[brew installation](https://brew.sh/).

#### Install it with `pipx`:

```bash
pipx install kaskade
```

[pipx installation](https://pipx.pypa.io/stable/installation/).

## Running kaskade

#### Admin view:

```bash
kaskade admin -b localhost:9092
```

#### Consumer view:

```bash
kaskade consumer -b localhost:9092 -t my-topic
```

## Configuration examples

#### Multiple bootstrap servers:

```bash
kaskade admin -b broker1:9092,broker2:9092
```

#### Consume and deserialize:

```bash
kaskade consumer -b localhost:9092 -t my-topic -k json -v json
```

#### Consuming from the beginning:

```bash
kaskade consumer -b localhost:9092 -t my-topic -x auto.offset.reset=earliest
```

#### Schema registry simple connection and avro deserialization:

```bash
kaskade consumer -b localhost:9092 -s url=http://localhost:8081 -t my-topic -k avro -v avro
```

> For more information about Schema Registry configurations go
> to: [Confluent Schema Registry client](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client).

#### SSL encryption example:

```bash
kaskade admin -b ${BOOTSTRAP_SERVERS} -x security.protocol=SSL
```

> For more information about SSL encryption and SSL authentication go
> to: [SSL support in librdkafka](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client).

#### Confluent cloud admin and consumer:

```bash
kaskade admin -b ${BOOTSTRAP_SERVERS} \
        -x security.protocol=SASL_SSL \
        -x sasl.mechanism=PLAIN \
        -x sasl.username=${CLUSTER_API_KEY} \
        -x sasl.password=${CLUSTER_API_SECRET}
```

```bash
kaskade consumer -b ${BOOTSTRAP_SERVERS} \
        -x security.protocol=SASL_SSL \
        -x sasl.mechanism=PLAIN \
        -x sasl.username=${CLUSTER_API_KEY} \
        -x sasl.password=${CLUSTER_API_SECRET} \
        -s url=${SCHEMA_REGISTRY_URL} \
        -s basic.auth.user.info=${SR_API_KEY}:${SR_API_SECRET} \
        -t my-topic \
        -k string \
        -v avro
```

> More about confluent cloud configuration
> at: [Kafka Client Quick Start for Confluent Cloud](https://docs.confluent.io/cloud/current/client-apps/config-client.html).

#### Running with docker:

```bash
docker run --rm -it --network my-networtk sauljabin/kaskade:latest \
    admin -b my-kafka:9092
```

```bash
docker run --rm -it --network my-networtk sauljabin/kaskade:latest \
    consumer -b my-kafka:9092 -t my-topic
```

## Development

For development instructions see [DEVELOPMENT.md](https://github.com/sauljabin/kaskade/blob/main/DEVELOPMENT.md).
