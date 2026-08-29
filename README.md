<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" width="400" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/banner.svg"></a>
</p>

<p align="center">
<a href="https://github.com/sauljabin/kaskade/actions/workflows/main.yml"><img alt="CI status" src="https://img.shields.io/github/actions/workflow/status/sauljabin/kaskade/main.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white&label=ci"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade?style=flat-square&logo=opensourceinitiative&logoColor=white&label=license"></a>
<a href="https://github.com/sponsors/sauljabin"><img alt="Sponsor on GitHub" src="https://img.shields.io/badge/sponsor-GitHub-EA4AAA?style=flat-square&logo=githubsponsors&logoColor=white"></a>
</p>

<p align="center">
<a href="https://pypi.org/project/kaskade"><img alt="PyPI version" src="https://img.shields.io/pypi/v/kaskade?style=flat-square&logo=pypi&logoColor=white&label=pypi"></a>
<a href="https://formulae.brew.sh/formula/kaskade"><img alt="Homebrew version" src="https://img.shields.io/homebrew/v/kaskade?style=flat-square&logo=homebrew&logoColor=white&label=homebrew"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade/tags"><img alt="Docker version" src="https://img.shields.io/docker/v/sauljabin/kaskade?style=flat-square&logo=docker&logoColor=white&label=docker"></a>
</p>

<p align="center">
<a href="https://pypi.org/project/kaskade"><img alt="Linux support" src="https://img.shields.io/badge/os-Linux-blue?style=flat-square&logo=linux&logoColor=white"></a>
<a href="https://pypi.org/project/kaskade"><img alt="macOS support" src="https://img.shields.io/badge/os-macOS-blue?style=flat-square&logo=apple&logoColor=white"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Supported Python versions" src="https://img.shields.io/pypi/pyversions/kaskade?style=flat-square&logo=python&logoColor=white&label=python"></a>
</p>

Bring Kafka along for the terminal ride. Kaskade gives you a stylish, keyboard-friendly way to explore clusters, manage topics, and consume records.

## Features

| Area | Capability | Availability |
| --- | --- | --- |
| General | Customize themes and keybindings | Supported |
| Admin | Browse topics, partitions, groups, and group members | Supported |
| Admin | View topic lag, replicas, and record counts | Supported |
| Admin | Create, edit, and delete topics | Supported, except changing the replication factor |
| Admin | Filter topics by name | Supported |
| Admin | Copy topic names to the clipboard | Supported in [OSC 52-compatible terminals](https://github.com/sauljabin/kaskade/blob/main/USAGE.md#osc-52-compatibility) |
| Admin | Refresh topic metadata and metrics | Automatic every 30 seconds, configurable, or manual |
| Consumer | Deserialize keys and values as bytes, JSON, string, integer, long, float, boolean, or double | Supported |
| Consumer | Filter records by key, value, header, and/or partition | Supported |
| Consumer | Copy individual records as JSON | Supported in [OSC 52-compatible terminals](https://github.com/sauljabin/kaskade/blob/main/USAGE.md#osc-52-compatibility) |
| Consumer | Export individual records as JSON | Supported |
| Consumer | Deserialize with Schema Registry | Avro and JSON are supported; Protobuf is not supported |
| Consumer | Deserialize without Schema Registry | Avro and Protobuf are supported |

## Screenshots

<table width="100%">
  <tr>
    <th width="50%">Admin</th>
    <th width="50%">Consumer</th>
  </tr>
  <tr>
    <td width="50%">
      <img alt="Kaskade admin mode" width="100%" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/admin.svg">
    </td>
    <td width="50%">
      <img alt="Kaskade consumer mode" width="100%" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/consumer.svg">
    </td>
  </tr>
</table>

## Quick start

### Homebrew

```bash
brew install kaskade
```

### pipx

```bash
pipx install kaskade
```

### Connect to Kafka

Admin view:

```bash
kaskade admin -b my-kafka:9092
```

Consumer view:

```bash
kaskade consumer -b my-kafka:9092 -t my-topic
```

## Usage

For configuration and usage examples, see the [Kaskade usage guide](https://github.com/sauljabin/kaskade/blob/main/USAGE.md).

## Development

For development instructions, see the [Kaskade development guide](https://github.com/sauljabin/kaskade/blob/main/DEVELOPMENT.md).

## Releases

See [GitHub Releases](https://github.com/sauljabin/kaskade/releases) for release notes and downloadable artifacts.

## Questions

For Q&A go to [GitHub Discussions](https://github.com/sauljabin/kaskade/discussions/categories/q-a).

## Donations

If Kaskade is useful to you, consider [supporting its development on GitHub Sponsors](https://github.com/sponsors/sauljabin).

## Acknowledgements & Sponsorship

<p>
<a href="https://github.com/littlehorse-enterprises/littlehorse"><img alt="Sponsored by LittleHorse" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/littlehorse-badge.svg"></a>
<a href="https://textual.textualize.io/"><img alt="Built with Textual" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/textual-badge.svg"></a>
<a href="https://openai.com/codex/"><img alt="Assisted by Codex" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/codex-badge.svg"></a>
</p>
