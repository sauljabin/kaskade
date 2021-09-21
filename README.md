# kaskade

<a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/-python-success?logo=python&logoColor=white"></a>
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://img.shields.io/badge/status-wip-orange"></a>
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://badges.pufler.dev/updated/sauljabin/kaskade?label=updated"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://github.com/sauljabin/kaskade/actions"><img alt="GitHub Actions" src="https://img.shields.io/github/checks-status/sauljabin/kaskade/main?label=tests"></a>
<a href="https://app.codecov.io/gh/sauljabin/kaskade"><img alt="Codecov" src="https://img.shields.io/codecov/c/github/sauljabin/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Version" src="https://img.shields.io/pypi/v/kaskade"></a>
<a href="https://libraries.io/pypi/kaskade"><img alt="Dependencies" src="https://img.shields.io/librariesio/release/pypi/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/platform-linux%20%7C%20osx-blueviolet"></a>

`kaskade` is a terminal user interface for [kafka](https://kafka.apache.org/).

## Installation

Install with pip:
```sh
pip install kaskade
```

Upgrade with pip:
```sh
pip install --upgrade kaskade
```

## Usage

Help:
```sh
kaskade --help
```

Version:
```sh
kaskade --version
```

## Development

Installing poetry:
```sh
pip install poetry
```

Installing development dependencies:
```sh
poetry install
```

Running unit tests:
```sh
poetry run python -m scripts.tests
```

Running multi version tests (`3.7`, `3.8`, `3.9`):

> Make sure you have `python3.7`, `python3.8`, `python3.9` aliases installed

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

Running cli using `poetry`:
```sh
poetry run kaskade
```
