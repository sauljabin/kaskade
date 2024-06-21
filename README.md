<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/banner.png"></a>
</p>
<a href="https://github.com"><img alt="GitHub" width="60" height="20" src="https://img.shields.io/badge/-github-blueviolet?logo=github&logoColor=white"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://github.com/sauljabin/kaskade/actions"><img alt="GitHub Workflow Status" src="https://img.shields.io/github/actions/workflow/status/sauljabin/kaskade/main.yml?branch=main"></a>
<a href="https://app.codecov.io/gh/sauljabin/kaskade"><img alt="Codecov" src="https://img.shields.io/codecov/c/github/sauljabin/kaskade"></a>
<br>
<a href="https://www.python.org/"><img alt="Python" width="60" height="20" src="https://img.shields.io/badge/-python-brightgreen?logo=python&logoColor=white"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Version" src="https://img.shields.io/pypi/v/kaskade?label="></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade?label="></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/-linux%20%7C%20osx-blue"></a>
<br>
<a href="https://www.docker.com/"><img alt="Docker" width="60" height="20" src="https://img.shields.io/badge/-docker-blue?logo=docker&logoColor=white"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="Docker Image Version (latest by date)" src="https://img.shields.io/docker/v/sauljabin/kaskade?label="></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="Docker Image Size (latest by date)" src="https://img.shields.io/docker/image-size/sauljabin/kaskade?label="></a>

# Kaskade

Kaskade is a text user interface (TUI) for Apache Kafka, built with [Textual](https://github.com/Textualize/textual).

# Features

- List topics, partitions, groups, members
- Topic information like lag, replicas, records count
- Consume from a topic
- Schema registry support
- String, Avro, Json and Protobuf deserialization
- Secure connection

# Screenshots

<p align="center">
<img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/dashboard.png">
</p>

<p align="center">
<img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/consumer.png">
</p>

# Installation

Install with `pipx`:

```shell
pipx install kaskade
```

> `pipx` will install `kaskade` and `kskd` aliases.

Upgrade with `pipx`:

```shell
pipx upgrade kaskade
```

# Running Kaskade

Pass the option `-b` (boostrap servers):

```shell
kaskade -b localhost:9092
```

Help:

```shell
kaskade --help
```

# Configuration Examples

### SSL encryption example:

```bash
kaskade -b localhost:9092 -X security.protocol=SSL
```

For more information about SSL encryption and SSL authentication go
to `librdkafka` official page: [Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client).

### Multiple bootstrap servers:

```bash
kaskade -b broker1:9092,broker2:9092
```

### Schema Registry simple connection:

```bash
kaskade -b localhost:9092 -S url=http://localhost:8081
```

More Schema Registry configurations at: [confluent-kafka-python documentation](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client).

### Confluent Cloud:

```bash
kaskade -b ${BOOTSTRAP_SERVERS} \
        -X security.protocol=SASL_SSL \
        -X sasl.mechanism=PLAIN \
        -X sasl.username=${CLUSTER_API_KEY} \
        -X sasl.password=${CLUSTER_API_SECRET} \
        -S url=${SCHEMA_REGISTRY_URL} \
        -S basic.auth.user.info=${SR_API_KEY}:${SR_API_SECRET}
```

# Development

For development instructions see [DEVELOPMENT.md](DEVELOPMENT.md).