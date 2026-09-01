# CLI Parameter Improvements

## Objective

Improve the readability, discoverability, and consistency of the `admin` and
`consumer` command-line interfaces while preserving their repeatable-property
configuration model for v5.

The repeatable `property=value` options are intentional and remain the primary
interface for Kafka, AWS, Avro, Protobuf, and Schema Registry configuration:

```bash
--config property=value
--aws property=value
--avro property=value
--protobuf property=value
--registry property=value
```

This keeps Kaskade extensible as the underlying clients add properties and
avoids duplicating every client setting as a Kaskade-specific option.

## Current Assessment

The CLI is suitable for v5. Its command names, common short options, grouped
help, examples, defaults, and validation are consistent with modern Python and
Kafka-oriented command-line tools.

The `admin` interface is compact and easy to scan. The `consumer` interface is
more complex by nature, but its help can better distinguish connection,
consumption, and deserialization concerns. The largest visual distraction in
both commands is the complete theme list rendered inline. Requiring `-b` also
duplicates `bootstrap.servers` when users already provide it through Kafka
client configuration.

These improvements are usability and documentation work; none is a release
blocker.

## Design Decisions

### Preserve repeatable property options

Do not introduce dedicated aliases for individual Avro, Protobuf, Schema
Registry, AWS, or Kafka properties in v5. Continue validating known
Kaskade-owned property sets before constructing clients, while allowing the
generic Kafka and Schema Registry configuration surfaces to follow their
underlying libraries.

Use consistent terminology in help text:

- Call the value a `property=value` pair.
- Use `Repeatable.` instead of phrases such as “Multiple options are allowed.”
- State when an option is required by a selected deserializer.
- Capitalize product and format names consistently: Kafka client, Avro,
  Protobuf, and Schema Registry.

### Resolve bootstrap servers from Kafka configuration

Make `-b/--bootstrap-servers` optional for both commands. When it is omitted,
accept `bootstrap.servers` from `--config-file` or a repeatable `--config`
entry. After merging the Kafka configuration sources, require a non-empty
`bootstrap.servers` value and report a CLI error before constructing the
application if none is available.

The application header must continue to display the resolved
`bootstrap.servers` value regardless of which source supplied it.

Document the effective configuration precedence:

1. `--config-file` supplies the base Kafka properties.
2. Repeatable `--config property=value` entries override matching file values.
3. When supplied, `-b/--bootstrap-servers` sets `bootstrap.servers` and always
   wins.
4. `--aws property=value` applies the security properties controlled by the AWS
   authentication integration.

This makes the explicit option an override rather than a separate required
source while keeping connection precedence deterministic.

## Proposed Help Structure

### Admin

```text
Kafka connection options:
  -b, --bootstrap-servers host:port
  -c, --config property=value
      --config-file filename

AWS options:
      --aws property=value

Application options:
      --theme name
      --refresh-interval seconds
      --help
```

### Consumer

```text
Kafka connection options:
  -b, --bootstrap-servers host:port
  -c, --config property=value
      --config-file filename

AWS options:
      --aws property=value

Consumption options:
  -t, --topic name
      --earliest
      --partition partition[:offset|earliest]

Deserialization options:
  -k, --key format
  -v, --value format

Avro options:
      --avro property=value

Protobuf options:
      --protobuf property=value

Schema Registry options:
      --registry property=value

Application options:
      --theme name
      --help
```

This structure moves `--earliest` out of Kafka connection configuration and
separates the topic position from record decoding.

## Implementation Plan

### 1. Extract shared option declarations

In `kaskade/main.py`, introduce focused decorator helpers for the option groups
shared by `admin` and `consumer`:

- Kafka connection options: bootstrap servers, inline properties, and property
  file.
- AWS options.
- Application options where sharing does not obscure command-specific options.

Keep each helper small and declarative. Do not change callback behavior,
parameter names, defaults, or configuration precedence during this refactor.

### 2. Reorganize the consumer groups

- Rename `Kafka options` to `Kafka connection options` in both commands.
- Rename `Topic options` to `Consumption options`.
- Move `--earliest` beside `--topic` and `--partition`.
- Move `--key` and `--value` into a new `Deserialization options` group.
- Rename `Other options` to `Application options` if Cloup permits the help
  option to be presented consistently there; otherwise retain Cloup's automatic
  help section and use `Application options` for theme and refresh only.

This step changes presentation only. Existing invocations must continue to
parse identically.

### 3. Express the position constraint declaratively

Use a Cloup constraint to make the all-partitions starting-position flag and
repeatable partition selection mutually exclusive. The constraint must:

- reject `--earliest --partition ...` before application construction;
- appear in generated help output;
- retain a concise error that names both incompatible options.

Remove the manual `if earliest and partitions` branch after equivalent behavior
is covered by the command declaration and tests.

### 4. Resolve bootstrap servers after merging Kafka properties

Make the shared `-b/--bootstrap-servers` parameter optional and introduce a
focused configuration helper used by both commands. It must:

- load `--config-file` properties first;
- overlay repeatable `--config property=value` entries;
- overlay `bootstrap.servers` only when `-b/--bootstrap-servers` was supplied;
- reject a missing or empty resolved `bootstrap.servers` value with a concise
  error that names `-b`, `--config-file`, and `--config`; and
- return the merged configuration before AWS-controlled security properties are
  applied.

Keep this resolution path shared so admin and consumer cannot drift in
precedence or validation behavior. The inferred value must flow through the
same Kafka configuration object used by the clients and application header.

### 5. Polish option help text

Rewrite the help constants and format-specific descriptions so that they are
short enough to wrap cleanly at the default terminal width.

Recommended wording:

```text
Bootstrap servers. Comma-separated host:port pairs; overrides
bootstrap.servers from Kafka client configuration.

Kafka client property. Repeatable; overrides matching properties from
--config-file.

Kafka client property file in property=value format.

Avro deserializer property. Repeatable; required when the key or value format
is avro. Properties: key, value, framing.
```

Apply equivalent language to AWS, Protobuf, and Schema Registry options.
Preserve the detailed accepted values in documentation when keeping all of them
in command help would make the output difficult to scan.

### 6. Reduce theme noise in generated help

Keep the existing `Choice` validation and default, but render the argument as
`name` instead of printing every available Textual theme in the option column.
Mention that a valid Textual theme name is required and point users to the
in-application theme command or the theme section in `USAGE.md`.

If Cloup cannot override the displayed metavar without weakening validation,
introduce a small validating parameter type rather than moving validation into
the application startup path.

### 7. Document behavior and precedence

Update `USAGE.md` with:

- the Kafka property precedence and bootstrap-server resolution rules;
- examples omitting `-b` when `bootstrap.servers` comes from `--config-file` or
  `--config`;
- one example showing explicit `-b` overriding a configured
  `bootstrap.servers` value;
- the purpose and repeatability of the format-specific property options;
- a link to the available property names and examples already maintained in the
  deserialization sections.

Update `README.md` only where it duplicates affected command examples. Update
`AGENT.md` so its durable CLI conventions reflect bootstrap resolution and help
grouping.

### 8. Extend tests

Add or update unit tests in `tests/unit/tests_main.py` for:

- the new admin and consumer help group names;
- `--earliest` appearing under consumption rather than connection options;
- key and value formats appearing under deserialization options;
- the theme metavar not expanding into the complete choice list;
- `--earliest` conflicting with `--partition`;
- omission of `-b` failing when no Kafka configuration source supplies a
  non-empty `bootstrap.servers` value;
- omission of `-b` succeeding when `bootstrap.servers` comes from either
  `--config-file` or `--config` for both admin and consumer;
- configuration precedence remaining file, inline property, optional explicit
  bootstrap override, then AWS-controlled security settings;
- unchanged behavior for repeatable Kafka, AWS, Avro, Protobuf, and Schema
  Registry properties.

Prefer assertions on meaningful headings, option names, errors, and constructed
configuration. Avoid snapshots of the entire help output because wrapping can
change between Click or Cloup releases.

### 9. Verify the complete change

Run:

```bash
uv run --locked kaskade admin --help
uv run --locked kaskade consumer --help
uv run --locked python -m scripts.tests
uv run --locked python -m scripts.styles
uv run --locked python -m scripts.analyze
```

Manually inspect both help screens at typical widths, including an 80-column
terminal, to ensure headings and property descriptions remain easy to scan.

## Acceptance Criteria

- Existing v5 commands using repeatable `property=value` options continue to
  work unchanged.
- Admin and consumer use the same names and wording for shared connection
  options.
- Consumer help clearly separates connection, consumption, and deserialization.
- The incompatibility between whole-topic earliest consumption and explicit
  partition selection is visible in help and enforced before application
  startup.
- Both commands accept a non-empty `bootstrap.servers` value from
  `--config-file` or `--config` when `-b` is omitted.
- An explicit `-b/--bootstrap-servers` value overrides configured
  `bootstrap.servers`, and startup fails clearly when no source supplies one.
- Theme validation remains strict without rendering the complete theme catalog
  inline.
- Kafka configuration precedence is documented and protected by tests.
- Documentation examples, unit tests, formatting, and static analysis all pass.

## Out of Scope for v5

- Dedicated flags or aliases for individual Kafka, AWS, Avro, Protobuf, or
  Schema Registry properties.
- Renaming or removing established options.
- Changing deserializer defaults or partition-selection semantics.
- Changing the configuration formats of Kafka property files or Kaskade's YAML
  settings.
