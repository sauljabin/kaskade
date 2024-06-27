<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" width="400" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/banner.png"></a>
</p>
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" height="20" src="https://img.shields.io/badge/-github-blueviolet?logo=github&logoColor=white"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Version" src="https://img.shields.io/pypi/v/kaskade?label=latest"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade?label=python"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/os-linux%20%7C%20macos-blue"></a>

## Kaskade

Kaskade is a text user interface (TUI) for Apache Kafka, built with [Textual](https://github.com/Textualize/textual).
It includes features like:

- Admin:
    - List topics, partitions, groups and group members
    - Topic information like lag, replicas, records count
    - Create and delete topics
- Consumer:
    - Json, string, integer and double deserialization

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

Install with `pipx`:

```shell
pipx install kaskade
```

> `pipx` will install `kaskade` and `kskd` aliases.

Upgrade with `pipx`:

```shell
pipx upgrade kaskade
```

<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="docker image available" height="20" src="https://img.shields.io/badge/-docker image available-blue?logo=docker&logoColor=white"></a>

## Running kaskade

Help:

```shell
kaskade --help
kaskade admin --help
kaskade consumer --help
```

Admin view:

```shell
kaskade admin -b localhost:9092
```

Consumer view:

```shell
kaskade consumer -b localhost:9092 -t my-topic
```

## Configuration examples

SSL encryption example:

```shell
kaskade admin -b localhost:9092 -x security.protocol=SSL
```

> For more information about SSL encryption and SSL authentication go
> to the `librdkafka` official
> page: [Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client).

Multiple bootstrap servers:

```shell
kaskade admin -b broker1:9092,broker2:9092
```

Confluent cloud:

```shell
kaskade admin -b ${BOOTSTRAP_SERVERS} \
        -x security.protocol=SASL_SSL \
        -x sasl.mechanism=PLAIN \
        -x sasl.username=${CLUSTER_API_KEY} \
        -x sasl.password=${CLUSTER_API_SECRET}
```

Consume and deserialize:

```shell
kaskade consumer -b localhost:9092 -t my-topic -k json -v json
```

Consuming from the beginning:

```shell
kaskade consumer -b localhost:9092 -x auto.offset.reset=earliest
```

## Development

For development instructions see [DEVELOPMENT.md](DEVELOPMENT.md).