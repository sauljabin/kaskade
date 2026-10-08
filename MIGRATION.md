# Migration

Steps to upgrade Kaskade between major versions. Release notes are on
[GitHub Releases](https://github.com/sauljabin/kaskade/releases).

## v5 to v6

- **Bootstrap servers:** `--bootstrap-servers` is now `-b/--bootstrap-server`.
  It is repeatable and still accepts a comma-separated list:
  `-b a:9092,b:9092` or `-b a:9092 -b b:9092`. The `-b` short form is
  unchanged.
- **Timeouts:** `--config-file` no longer accepts a `[timeouts]` section. Move
  the values to `settings.yaml`:

  ```yaml
  admin:
    timeouts:
      read: 10
      write: 60
  consumer:
    timeouts:
      poll: 0.5
      idle: 2.5
      assignment: 15
      request: 10
  ```

  `--timeout` now accepts only the current command's properties: `admin.*` for
  `admin`, `consumer.*` for `consumer`.
- **Docker:** images are no longer published. Install with `brew install kaskade`
  or `pipx install kaskade`.

## v4 to v5

- **Kafka properties:** `-c/--config property=value` is now
  `--kafka property=value`.
- **Configuration file:** `--config-file` reads an INI file instead of a
  Java properties file. Put Kafka properties under `[kafka]`, Schema Registry
  properties under `[registry]`, and AWS settings under `[aws]`. See
  [examples/client.ini](examples/client.ini).
- **Read from the beginning:** `--from-beginning` is now `--earliest`.
- **Bytes:** byte keys and values show as Base64 instead of Python's `b'...'`
  form. Choose another format with `--bytes encoding=hex`, `byte-array`, or
  `escaped`.
- **Local JSON, Avro, and Protobuf:** Confluent framing is no longer detected
  automatically. For payloads written by Confluent serializers, add
  `framing=confluent`, for example `--json framing=confluent`.
