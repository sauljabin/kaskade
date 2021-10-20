<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/banner.png"></a>
</p>
<p align="center">
<a href="https://github.com"><img alt="GitHub" src="https://img.shields.io/badge/-github-0da5e0?logo=github&logoColor=white"></a>
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://img.shields.io/badge/status-wip-orange"></a>
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://badges.pufler.dev/updated/sauljabin/kaskade?label=updated"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://github.com/sauljabin/kaskade/actions"><img alt="GitHub Workflow Status" src="https://img.shields.io/github/workflow/status/sauljabin/kaskade/CI?label=tests"></a>
<a href="https://app.codecov.io/gh/sauljabin/kaskade"><img alt="Codecov" src="https://img.shields.io/codecov/c/github/sauljabin/kaskade"></a>
<a href="https://pre-commit.com/"><img alt="Pre-commit" src="https://img.shields.io/badge/pre--commit-enabled-brightgreen"></a>
<br>
<a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/-python-brightgreen?logo=python&logoColor=white"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Version" src="https://img.shields.io/pypi/v/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade"></a>
<a href="https://libraries.io/pypi/kaskade"><img alt="Dependencies" src="https://img.shields.io/librariesio/release/pypi/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/platform-linux%20%7C%20osx-0da5e0"></a>
<a href="https://github.com/psf/black"><img alt="Code Style" src="https://img.shields.io/badge/code%20style-black-black"></a>
<br>
<a href="https://www.docker.com/"><img alt="Docker" src="https://img.shields.io/badge/-docker-blue?logo=docker&logoColor=white"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="Docker Image Version (latest by date)" src="https://img.shields.io/docker/v/sauljabin/kaskade?label=tag"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade"><img alt="Docker Image Size (latest by date)" src="https://img.shields.io/docker/image-size/sauljabin/kaskade"></a>
<br>
<a href="https://kafka.apache.org/"><img alt="Kafka" src="https://img.shields.io/badge/-kafka-e3e3e3?logo=apache-kafka&logoColor=202020"></a>
<a href="https://kafka.apache.org/"><img alt="Kafka" src="https://img.shields.io/badge/kafka-2.8%20%7C%203.0-blue"/></a>
<a href="https://pypi.org/project/confluent-kafka/"><img alt="Kafka Client" src="https://img.shields.io/pypi/v/confluent-kafka?label=kafka%20client"></a>
</p>

**kaskade** is a tui (terminal user interface) for [kafka](https://kafka.apache.org/).
It is built on [textual](https://github.com/willmcgugan/textual) tui framework and [rich](https://github.com/willmcgugan/rich) lib.

For a local kafka environment go to https://github.com/sauljabin/kafka-docker.

**NOTE:** This project is currently a work in progress, but usable by early
adopters. [textual](https://github.com/willmcgugan/textual) is also a work in progress project.

# Table of Contents

* [Installation and Usage](#installation-and-usage)
* [Running with Docker](#running-with-docker)
* [Configuration](#configuration)
* [Screenshots](#screenshots)
* [Alternatives](#alternatives)
* [To Do](#to-do)
* [Development](#development)
  * [Scripts](#scripts)
  * [Docker](#docker)
  * [Bumping Version](#bumping-version)

# Installation and Usage

Install with pip:

```sh
pip install kaskade
```

> `pip` will install `kaskade` and `kskd` aliases.

Upgrade with pip:

```sh
pip install --upgrade kaskade
```

Help:

```sh
kaskade --help
```

Version:

```sh
kaskade --version
```

Run without config file (it'll take any of `kaskade.yml`, `kaskade.yaml`, `config.yml` or `config.yaml`):

```sh
kaskade
```

Run with config file:

```sh
kaskade my-file.yml
```

# Running with Docker

Using docker (remember to set a `network` and `volume`):

```sh
docker run --rm -it --network kafka-sandbox_network \
--volume $(pwd)/config.yml:/kaskade/config.yml \
sauljabin/kaskade:latest
```

Aliases:

```sh
alias kaskade='docker run --rm -it --network kafka-sandbox_network \
--volume $(pwd):/kaskade \
sauljabin/kaskade:latest'

alias kskd=kaskade
```

> These aliases will mount the current directory as a volume.

# Configuration

A default [yaml](https://yaml.org/spec/1.2/spec.html) configuration file name can be either `kaskade.yml`
, `kaskade.yaml`, `config.yml` or `config.yaml`. It supports all the configuration
on [kafka consumer configuration](https://kafka.apache.org/documentation/#consumerconfigs) page.

Simple connection example:

```yml
kafka:
  bootstrap.servers: localhost:9093
```

SSL encryption example:

```yml
kafka:
  bootstrap.servers: kafka:9092
  security.protocol: SSL
  ssl.truststore.location: {{path}}/truststore.jks
  ssl.truststore.password: {{password}}
```

SSL auth example:

```yml
kafka:
  bootstrap.servers: kafka:9092
  security.protocol: SSL
  ssl.truststore.location: {{path}}/truststore.jks
  ssl.truststore.password: {{password}}
  ssl.keystore.location: {{path}}/keystore.jks
  ssl.keystore.password: {{password}}
  ssl.key.password: {{password}}
```

Support for env variables:

```yml
kafka:
  bootstrap.servers: ${BOOTSTRAP_SERVERS}
```

# Screenshots

<p align="center">
<img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/dashboard.png">
</p>

<p align="center">
<img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/help.png">
</p>

# Alternatives

- cli [kcat](https://github.com/edenhill/kcat)
- cli [zoe](https://github.com/adevinta/zoe)
- cli [kaf](https://github.com/birdayz/kaf)
- wui [akhq](https://github.com/tchiotludo/akhq)
- tui [kcli](https://github.com/cswank/kcli)

# To Do

- Consumed messages table
- Consumer group lag
- Interactive search and filters
- Topic size and count
- Schema registry support
- Increment test coverage

# Development

Installing poetry:

```sh
pip install poetry
```

Installing development dependencies:

```sh
poetry install
```

Installing pre-commit hooks:

```sh
poetry run pre-commit install
```

Running kaskade:

```sh
poetry run kaskade
```

### Scripts

Running unit tests:

```sh
poetry run python -m scripts.tests
```

Running multi-version tests ([versions](https://github.com/sauljabin/kaskade/blob/main/.github/workflows/main.yml#L17)):

```sh
poetry run python -m scripts.multi-version-tests
```

Applying code styles:

```sh
poetry run python -m scripts.styles
```

Running code analysis:

```sh
poetry run python -m scripts.analyze
```

Running code coverage:

```sh
poetry run python -m scripts.tests-coverage
```

Running pre-commit hooks:

```sh
poetry run python -m scripts.pre-commit
```

Generate readme banner:

```sh
poetry run python -m scripts.banner
```

### Docker

Build docker:

```sh
poetry run python -m scripts.docker-build
```

> Image tag `sauljabin/kaskade:latest`.

Run with docker (create a `config.yml` file):

```sh
docker run --rm -it --network kafka-sandbox_network \
--volume $(pwd)/config.yml:/kaskade/config.yml \
sauljabin/kaskade:latest
```

### Bumping Version

Help:

```sh
poetry run python -m scripts.release --help
```

> More info at https://python-poetry.org/docs/cli/#version and https://semver.org/.

Upgrade (`major.minor.patch`):

```sh
poetry run python -m scripts.release patch
```
