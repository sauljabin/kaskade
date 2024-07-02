<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" width="400" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/banner.png"></a>
</p>

<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://img.shields.io/badge/-github-blueviolet?logo=github&logoColor=white"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="DockerHub" src="https://img.shields.io/badge/-docker-blue?logo=docker&logoColor=white"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Version" src="https://img.shields.io/pypi/v/kaskade?label=latest"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade?label=python"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/os-linux%20%7C%20macos-blue"></a>
<a href="https://libraries.io/pypi/kaskade"><img alt="Libraries.io dependency status for latest release" src="https://img.shields.io/librariesio/release/pypi/kaskade"></a>

## Kaskade

Kaskade is a text user interface (TUI) for Apache Kafka, built with [Textual](https://github.com/Textualize/textual).
It includes features like:

- Admin:
    - List topics, partitions, groups and group members
    - Topic information like lag, replicas and records count
    - Create, edit and delete topics
    - Filter topics by name
- Consumer:
    - Json, string, integer, long, float, boolean and double deserialization
    - Filter by key, value, header and/or partition
    - Schema Registry support with avro

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

#### Install with `pipx`:

```shell
pipx install kaskade
```

> `pipx` will install `kaskade` and `kskd` aliases.

#### Upgrade with `pipx`:

```shell
pipx upgrade kaskade
```

> How to install pipx at: https://pipx.pypa.io/stable/installation/

## Running kaskade

#### Help:

```shell
kaskade --help
kaskade admin --help
kaskade consumer --help
```

#### Admin view:

```shell
kaskade admin -b localhost:9092
```

#### Consumer view:

```shell
kaskade consumer -b localhost:9092 -t my-topic
```

#### Running with docker:

```shell
docker run --rm -it --network my-networtk sauljabin/kaskade:latest admin -b kafka1:9092
docker run --rm -it --network my-networtk sauljabin/kaskade:latest consumer -b kafka1:9092 -t my-topic
```

## Configuration examples

#### Multiple bootstrap servers:

```shell
kaskade admin -b broker1:9092,broker2:9092
```

#### Consume and deserialize:

```shell
kaskade consumer -b localhost:9092 -t my-topic -k json -v json
```

#### Consuming from the beginning:

```shell
kaskade consumer -b localhost:9092 -t my-topic -x auto.offset.reset=earliest
```

#### Schema registry simple connection and avro deserialization:

```shell
kaskade consumer -b localhost:9092 -s url=http://localhost:8081 -t my-topic -k avro -v avro
```

> More Schema Registry configurations
> at: [SchemaRegistryClient](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client).

> librdkafka clients do not currently support AVRO Unions in (de)serialization, more
> at: [Limitations for librdkafka clients](https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/serdes-avro.html#limitations-for-librdkafka-clients).

#### SSL encryption example:

```shell
kaskade admin -b ${BOOTSTRAP_SERVERS} -x security.protocol=SSL
```

> For more information about SSL encryption and SSL authentication go
> to the `librdkafka` official
>
page: [Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client).

#### Confluent cloud admin:

```shell
kaskade admin -b ${BOOTSTRAP_SERVERS} \
        -x security.protocol=SASL_SSL \
        -x sasl.mechanism=PLAIN \
        -x sasl.username=${CLUSTER_API_KEY} \
        -x sasl.password=${CLUSTER_API_SECRET}
```

#### Confluent cloud consumer:

```shell
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

## Development

For development instructions see [DEVELOPMENT.md](DEVELOPMENT.md).