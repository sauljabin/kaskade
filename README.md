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
<br>
<a href="https://pypi.org/project/kaskade"><img alt="Linux support" src="https://img.shields.io/badge/os-Linux-7C3AED?style=flat-square&logo=linux&logoColor=white"></a>
<a href="https://pypi.org/project/kaskade"><img alt="macOS support" src="https://img.shields.io/badge/os-macOS-7C3AED?style=flat-square&logo=apple&logoColor=white"></a>
</p>

Kaskade is a terminal UI for Kafka. `kaskade admin` shows your topics,
partitions, and consumer groups and lets you create, edit, and delete topics.
`kaskade consumer` reads records from a topic and decodes them as JSON, Avro,
or Protobuf, with or without Schema Registry. Everything works from the
keyboard.

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
- Inspect topic configuration, lag, replicas, and record counts
- Create, edit, delete, and filter topics without leaving the TUI
- Refresh topic metadata and metrics every 30 seconds by default, or on demand

### Record consumption

- Deserialize keys and values as bytes, primitives, JSON, Avro, or Protobuf,
  including Confluent Schema Registry and native Apicurio Registry v3
- Resolve Registry Protobuf messages and referenced schemas without generated classes
- Choose raw, Apicurio, or Confluent framing separately for keys and values when decoding with local schemas
- Filter records by key, value, header, or partition
- Start from the earliest offsets or explicit partition/offset selections
- Keep consuming when a key, value, or header fails to decode, and show it as bytes next to the error
- Show bytes as Base64, hex, byte arrays, or escaped bytes
- Copy or export individual records as JSON

### Connections and configuration

- Keep Kafka, Registry, and AWS settings in an INI file, or pass them on the command line
- Raise operation timeouts for slow or distant clusters
- Connect through TLS, SASL, Confluent Cloud, or Amazon MSK IAM authentication
- Use Confluent Schema Registry, native Apicurio Registry, or Apicurio's
  Confluent-compatible API

### Terminal experience

- Navigate entirely by keyboard with arrow and Vim-style shortcuts
- Customize themes and keybindings
- Copy data through an [OSC 52-compatible terminal](https://github.com/sauljabin/kaskade/blob/main/USAGE.md#osc-52-compatibility)

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

## Documentation

- [Usage](https://github.com/sauljabin/kaskade/blob/main/USAGE.md): commands,
  settings, connections, and decoding.
- [Migration](https://github.com/sauljabin/kaskade/blob/main/MIGRATION.md):
  upgrading between major versions.
- [Development](https://github.com/sauljabin/kaskade/blob/main/DEVELOPMENT.md):
  working on Kaskade itself.
- [GitHub Releases](https://github.com/sauljabin/kaskade/releases): release
  notes and downloads.

## Questions

Ask in [GitHub Discussions](https://github.com/sauljabin/kaskade/discussions/categories/q-a).

## Security

Please report vulnerabilities privately, as described in the
[security policy](https://github.com/sauljabin/kaskade/blob/main/SECURITY.md).

## Donations

If Kaskade saves you time, you can
[sponsor it on GitHub](https://github.com/sponsors/sauljabin).

## AI Assistance

Kaskade is developed with AI assistance. Every AI-assisted change is reviewed
and tested before it's merged.

## Acknowledgements

<p>
<a href="https://github.com/littlehorse-enterprises/littlehorse"><img alt="Sponsored by LittleHorse" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/littlehorse-badge.svg"></a>
<a href="https://textual.textualize.io/"><img alt="Built with Textual" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/images/textual-badge.svg"></a>
</p>
