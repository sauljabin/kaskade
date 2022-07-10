<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/banner.png"></a>
</p>

<a href="https://github.com"><img alt="GitHub" src="https://img.shields.io/badge/-github-0da5e0?logo=github&logoColor=white"></a>
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://img.shields.io/badge/status-wip-orange"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://github.com/sauljabin/kaskade/actions"><img alt="GitHub Workflow Status" src="https://img.shields.io/github/workflow/status/sauljabin/kaskade/CI?label=tests"></a>
<a href="https://app.codecov.io/gh/sauljabin/kaskade"><img alt="Codecov" src="https://img.shields.io/codecov/c/github/sauljabin/kaskade"></a>
<br>
<a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/-python-brightgreen?logo=python&logoColor=white"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Version" src="https://img.shields.io/pypi/v/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade"></a>
<a href="https://libraries.io/pypi/kaskade"><img alt="Dependencies" src="https://img.shields.io/librariesio/release/pypi/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/platform-linux%20%7C%20osx-0da5e0"></a>
<br>
<a href="https://kafka.apache.org/"><img alt="Kafka" src="https://img.shields.io/badge/-kafka-e3e3e3?logo=apache-kafka&logoColor=202020"></a>
<a href="https://kafka.apache.org/"><img alt="Kafka" src="https://img.shields.io/badge/kafka-2.8%20%7C%203.0-blue"/></a>
<a href="https://pypi.org/project/confluent-kafka/"><img alt="Kafka Client" src="https://img.shields.io/pypi/v/confluent-kafka?label=kafka%20client"></a>
<br>
<a href="https://www.docker.com/"><img alt="Docker" src="https://img.shields.io/badge/-docker-blue?logo=docker&logoColor=white"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="Docker Image Version (latest by date)" src="https://img.shields.io/docker/v/sauljabin/kaskade?label=tag"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="Docker Image Size (latest by date)" src="https://img.shields.io/docker/image-size/sauljabin/kaskade"></a>

**kaskade** is a tui (text user interface) for [kafka](https://kafka.apache.org/).
:rocket: This project is powered by [textual](https://github.com/willmcgugan/textual)
and [rich](https://github.com/willmcgugan/rich)!.

For a local kafka environment go to https://github.com/sauljabin/kafka-docker.

> :construction: This project is currently a work in progress, but usable by early adopters.

# Table of Contents

- [Table of Contents](#table-of-contents)
- [Installation and Usage](#installation-and-usage)
- [Running with Docker](#running-with-docker)
- [Configuration](#configuration)
    - [Kafka](#kafka)
    - [Kaskade](#kaskade)
- [Screenshots](#screenshots)
- [Alternatives](#alternatives)
- [Development](#development)
    - [Scripts](#scripts)
    - [Docker](#docker)
    - [Bumping Version](#bumping-version)

# Installation and Usage

Install with pip:

```shell
pip install kaskade
```

> `pip` will install `kaskade` and `kskd` aliases.

Upgrade with pip:

```shell
pip install --upgrade kaskade
```

Help:

```shell
kaskade --help
```

Version:

```shell
kaskade --version
```

Information, it shows app information and some config examples:

```shell
kaskade --info
```

Run without config file (it'll take any of `kaskade.yml`, `kaskade.yaml`, `config.yml` or `config.yaml`):

```shell
kaskade
```

Run with config file:

```shell
kaskade my-config.yml
```

# Running with Docker

Using docker (remember to set a `network` and `volume`):

```shell
docker run --rm -it --network kafka \
--volume $(pwd):/kaskade \
sauljabin/kaskade:latest
```

Aliases:

```shell
alias kaskade='docker run --rm -it --network kafka \
--volume $(pwd):/kaskade \
sauljabin/kaskade:latest'
alias kskd=kaskade
```

> These aliases will mount the current directory as a volume.

# Configuration

A [yaml](https://yaml.org/spec/1.2/spec.html) configuration file (check [Installation and Usage](#installation-and-usage) section for more information).

### Kafka

Simple connection example:

```yaml
kafka:
  bootstrap.servers: localhost:9092
```

SSL encryption example:

```yaml
kafka:
  bootstrap.servers: localhost:9092
  security.protocol: SSL
```

> For more information about SSL encryption and SSL authentication go to [confluent-kafka](https://github.com/confluentinc/confluent-kafka-python#ssl-certificates) and [librdkafka](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client).

Support for env variables (example `BOOTSTRAP_SERVERS`):

```yaml
kafka:
  bootstrap.servers: ${BOOTSTRAP_SERVERS}
```

### Kaskade

Next settings are optional:

```yaml
kaskade:
  debug: off # default off
  refresh: on # enable auto-refresh default on
  refresh-rate: 5 # auto-refresh rate default 5 secs
```

> `debug` enabled will generate logs into a specific log file, execute `kaskade --info` to get the log path.

# Screenshots

<p align="center">
<img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/dashboard.png">
</p>

<p align="center">
<img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/help.png">
</p>

<p align="center">
<img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/consumer.png">
</p>

# Alternatives

- cli: [[kcat](https://github.com/edenhill/kcat), [zoe](https://github.com/adevinta/zoe), [kaf](https://github.com/birdayz/kaf)]
- wui: [[akhq](https://github.com/tchiotludo/akhq)]
- tui: [[kcli](https://github.com/cswank/kcli)]

# Development

Python supported versions:

<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade?label="></a>

Installing poetry:

```shell
pip install poetry
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
poetry run python -m scripts.tests-coverage
```

Running pre-commit hooks:

```shell
poetry run python -m scripts.pre-commit
```

Generate readme banner:

```shell
poetry run python -m scripts.banner
```

### Docker

Build docker:

```shell
poetry run python -m scripts.docker-build
```

> Image tag `sauljabin/kaskade:latest`.

Run with docker (create a `config.yml` file):

```shell
docker run --rm -it --network kafka \
--volume $(pwd):/kaskade \
sauljabin/kaskade:latest
```

### Bumping Version

Help:

```shell
poetry run python -m scripts.release --help
```

> More info at https://python-poetry.org/docs/cli/#version and https://semver.org/.

Upgrade (`major.minor.patch`):

```shell
poetry run python -m scripts.release patch
```
