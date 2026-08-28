<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" width="400" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/banner.svg"></a>
</p>

<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://img.shields.io/badge/github-blueviolet?logo=github&logoColor=white"></a>
<a href="https://github.com/sponsors/sauljabin"><img alt="donate" src="https://img.shields.io/badge/donate-EA4AAA?logo=github-sponsors&logoColor=white"></a>
<a href="https://libraries.io/pypi/kaskade"><img alt="Libraries.io dependency status for latest release" src="https://img.shields.io/librariesio/release/pypi/kaskade?logo=python&logoColor=white&label="></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Pypi Version" src="https://img.shields.io/pypi/v/kaskade"></a>
<a href="https://formulae.brew.sh/formula/kaskade"><img alt="Homebrew Version" src="https://img.shields.io/homebrew/v/kaskade"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade/tags"><img alt="Docker Version" src="https://img.shields.io/docker/v/sauljabin/kaskade?label=dockerhub"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/os-linux%20%7C%20macos-blue"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade?label=python"></a>
</p>

## Kaskade

Kaskade is a text user interface (TUI) for Apache Kafka.

It includes features like:

### Admin

- List topics, partitions, groups and group members.
- Topic information like lag, replicas and records count.
- Create, edit and delete topics.
- Filter topics by name.

### Consumer

- Json, string, integer, long, float, boolean and double deserialization.
- Filter by key, value, header and/or partition.
- Export individual consumed records as JSON.
- Schema Registry support for avro and json.
- Protobuf deserialization support without Schema Registry.
- Avro deserialization without Schema Registry.

## Limitations

Kaskade does not include:

- Schema Registry for protobuf.

## Screenshots

<table>
  <tr>
    <th>Admin</th>
    <th>Consumer</th>
  </tr>
  <tr>
    <td>
      <img alt="Kaskade admin mode" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/admin.svg">
    </td>
    <td>
      <img alt="Kaskade consumer mode" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/consumer.svg">
    </td>
  </tr>
</table>

## Installation

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
kaskade admin -b my-kafka:9092
```

#### Consumer view:

```bash
kaskade consumer -b my-kafka:9092 -t my-topic
```

## Usage

For configuration and usage examples, see [USAGE.md](USAGE.md).

## Development

For development instructions see [DEVELOPMENT.md](https://github.com/sauljabin/kaskade/blob/main/DEVELOPMENT.md).

## Releases

See [GitHub Releases](https://github.com/sauljabin/kaskade/releases) for release notes and downloadable artifacts.

## Questions

For Q&A go to [GitHub Discussions](https://github.com/sauljabin/kaskade/discussions/categories/q-a).

## Acknowledgements & Sponsorship

<p>
<a href="https://github.com/littlehorse-enterprises/littlehorse"><img alt="Sponsored by LittleHorse" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/littlehorse-badge.svg"></a>
<a href="https://textual.textualize.io/"><img alt="Built with Textual" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/textual-badge.svg"></a>
<a href="https://openai.com/codex/"><img alt="Assisted by Codex" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/codex-badge.svg"></a>
</p>
