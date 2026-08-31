<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" width="400" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/banner.svg"></a>
</p>

<p align="center">
<a href="https://github.com/sauljabin/kaskade/actions/workflows/main.yml"><img alt="CI status" src="https://img.shields.io/github/actions/workflow/status/sauljabin/kaskade/main.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white&label=ci"></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade?style=flat-square&logo=opensourceinitiative&logoColor=white&label=license"></a>
<a href="https://github.com/sponsors/sauljabin"><img alt="Sponsor on GitHub" src="https://img.shields.io/badge/sponsor-GitHub-EA4AAA?style=flat-square&logo=githubsponsors&logoColor=white"></a>
<br>
<a href="https://pypi.org/project/kaskade"><img alt="PyPI version" src="https://img.shields.io/pypi/v/kaskade?style=flat-square&logo=pypi&logoColor=white&label=pypi"></a>
<a href="https://formulae.brew.sh/formula/kaskade"><img alt="Homebrew version" src="https://img.shields.io/homebrew/v/kaskade?style=flat-square&logo=homebrew&logoColor=white&label=homebrew"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade/tags"><img alt="Docker version" src="https://img.shields.io/docker/v/sauljabin/kaskade?style=flat-square&logo=docker&logoColor=white&label=docker"></a>
</p>

Bring Kafka along for the terminal ride. Kaskade gives you a stylish, keyboard-friendly way to explore clusters, manage topics, and consume records.

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

## Features

### Kafka administration

- Browse topics, partitions, consumer groups, and group members
- Inspect topic lag, replicas, and record counts
- Create, edit, delete, and filter topics
- Refresh topic metadata and metrics automatically or manually
- Copy topic names to the clipboard

### Record consumption

- Deserialize keys and values as bytes, JSON, string, integer, long, float,
  boolean, or double
- Filter records by key, value, header, or partition
- Start from the earliest offsets or explicit partition/offset selections
- Keep malformed keys or values inspectable with visible BYTES fallback warnings
- Copy or export individual records as JSON
- Deserialize Avro and JSON data with Schema Registry
- Deserialize Avro and Protobuf data without Schema Registry

### Terminal experience

- Customize themes and keybindings
- Copy data through an [OSC 52-compatible terminal](https://github.com/sauljabin/kaskade/blob/main/USAGE.md#osc-52-compatibility)

## Current limitations

- Topic replication factors cannot be changed
- Schema Registry does not support Protobuf
- Clipboard integration requires an OSC 52-compatible terminal

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

## Security

Report suspected vulnerabilities privately by following the [Kaskade security policy](https://github.com/sauljabin/kaskade/blob/main/SECURITY.md).

## Donations

If Kaskade is useful to you, consider [supporting its development on GitHub Sponsors](https://github.com/sponsors/sauljabin).

## AI Assistance

This project uses AI-assisted development tools. Some code and documentation
may be generated or revised with AI assistance. All AI-assisted changes are
reviewed and tested by the maintainer before they are included.

## Acknowledgements

<p>
<a href="https://github.com/littlehorse-enterprises/littlehorse"><img alt="Sponsored by LittleHorse" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/littlehorse-badge.svg"></a>
<a href="https://textual.textualize.io/"><img alt="Built with Textual" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/textual-badge.svg"></a>
</p>
