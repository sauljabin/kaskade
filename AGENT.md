# Agent Instructions

## Engineering and Documentation

- Support Linux and macOS; keep paths, terminal input, and shell documentation
  portable.
- Keep cyclomatic complexity at or below 10. Ruff `C901` runs through
  `scripts.analyze`; prefer focused helpers over suppressions.
- Before finishing, review the complete diff for clarity, duplication, and
  maintainability, then rerun relevant analysis and tests.
- Keep this file and affected user documentation concise and current. Record
  stable conventions, remove obsolete or contradicted guidance, and avoid
  implementation history.
- Keep `USAGE.md` focused on end users. Document the development-only sandbox,
  its population tool, and its access requirements in `DEVELOPMENT.md` only.
- Importing `kaskade` must not create directories, open files, or modify the root
  logger. Configure the named logger lazily and tolerate an unavailable log
  destination.

## CLI and Configuration

- Share admin and consumer client configuration and Kafka connection
  declarations. Help groups are `Configuration options`, `Kafka connection
  options`, `AWS options`, and `Application options`; consumer also separates
  `Consumption options` and `Deserialization options`.
- Keep `--earliest` and `--partition` declaratively mutually exclusive. Render
  the theme argument as `name` without weakening choice validation.
- `--config-file client.ini` loads entries from optional `[kafka]`, `[registry]`,
  and `[aws]` INI sections. Merge each file section under its matching repeatable
  CLI option, then apply `-b/--bootstrap-servers`. Require a non-empty resolved
  `bootstrap.servers` and update `examples/client.ini` when this behavior changes.
- Forward arbitrary `--kafka` and `--registry` properties to their respective
  `confluent-kafka` clients and let those clients validate names and values.
- Keep `-k` as the short form of consumer `--key`; `--kafka` has no short form.
- Kaskade settings come from `KASKADE_CONFIG`, then
  `$XDG_CONFIG_HOME/kaskade/config.yaml`, then
  `~/.config/kaskade/config.yaml`. Ignore invalid entries, retain valid ones,
  warn in-app, and keep `examples/config.yaml` current when bindings change.
- Logs use `$XDG_STATE_HOME/kaskade/kaskade.log`, falling back to
  `~/.local/state/kaskade/kaskade.log`, and rotate at 5 MiB with three backups.
- `--aws region=<region>` enables Amazon MSK IAM in admin, consumer, and sandbox
  population. Validate repeatable `--aws property=value` settings before client
  construction. Do not raise the `aws-msk-iam-sasl-signer-python>=1.0` baseline
  without using newer functionality.
- Local JSON, Avro, and Protobuf use raw framing by default. Select Confluent
  framing explicitly through global or field-scoped properties; never infer it
  from payload bytes.

## Data Loading and Consumer Records

- Render topic metadata before record and consumer-group metrics. Batch
  partition-offset requests and bound consumer-group offset concurrency; do not
  create temporary consumers for admin metrics.
- Preserve the last complete metrics during refresh. Never overlap automatic,
  manual, resumed, or post-mutation refreshes; coalesce non-periodic requests in
  the shared refresh coordinator.
- Admin auto-refresh defaults to 30 seconds, pauses outside the topic list, and
  is configured by `admin.refresh_interval_seconds` or
  `admin --refresh-interval`; `0` disables it.
- `consumer --earliest` subscribes to all partitions with
  `auto.offset.reset=earliest`. Repeatable
  `--partition PARTITION[:OFFSET|earliest]` uses manual assignment and must not
  fetch unlisted partitions. Numeric offsets, including `0`, are absolute.
- Handle recognized key and value deserialization failures independently per
  record. Preserve the configured deserializer for later records, expose BYTES
  fallback diagnostics in details, tooltips, copy, and export, and keep broker
  failures and unexpected exceptions fatal.
- Details, copy, and export share the versionless record contract in
  `schemas/consumer-record.schema.json`. Keep its examples and conformance tests
  synchronized. In that contract:
  - Headers are ordered `{key, value}` objects. Add top-level `error` only when
    STRING header deserialization fails.
  - Key/value `deserializer` contains `type` and optional resolved Registry
    `schema`. Registry lookup is best-effort and cached by schema, topic, and
    field.
  - A key/value failure adds sibling `error` metadata with a BYTES `fallback`.
  - BYTES content stays directly in `content`; its deserializer or fallback has
    `encoding`. `--bytes` configures explicit BYTES fields globally or per field,
    while global-only `--fallback encoding=...` configures failures. Both default
    independently to Base64. Null content omits `encoding`.

## TUI Interaction

- Preserve arrows, `h`/`j`/`k`/`l`, and `g`/`G` navigation. Keep shortcuts safe
  for tmux and Zellij. Quit is `ctrl+c`; never add `ctrl+q` or a copy alias for
  `ctrl+c`.
- Use stable binding IDs represented in `KNOWN_BINDING_IDS`. Visible bindings
  need concise Title Case descriptions and useful tooltips; update examples and
  tests when adding or renaming them.
- Plain-character shortcuts must not intercept input. `?` opens Help normally;
  `f1` remains available from focused text inputs.
- Contextual entity copy uses `y` and Textual's OSC 52 API. Keep it out of the
  Footer but available in Help and Commands. `USAGE.md` owns the compatibility
  matrix. Selected-text copy is `Cmd+C` on macOS or `Ctrl+Shift+C` on Linux.
- Keep the command palette on `:` and `ctrl+p`. Include contextual actions,
  exclude duplicate navigation and maximize/minimize actions, and replace
  Textual's Keys command with contextual Kaskade Help.

### Footer and Help

Binding declaration order controls the Footer:

- Main screens: contextual actions, then `Quit`, `Help`, `Commands`.
- Action modals: primary action, `Back` or `Cancel`, then `Help`.
- Read-only modals: `Back`, then `Help`.
- Help: only `esc Back`.

Use `modal_bindings(...)` so Help is appended last. Do not put Help on the base
modal class, because inherited bindings are merged first. Show implicit primary
keys such as Enter in the Footer.

Help is a centered `ModalScreen` that snapshots and groups the underlying
screen's effective bindings. It must show every alias, focus its command table,
restore prior focus on close, use `Help — <Context>`, and show application and
project information above the commands. Use the standard Footer with only
`esc Back`; `?`, `f1`, and `q` may also close Help without duplicate Footer
entries.

## Layout and Themes

- Keep shared styling in `kaskade/styles.css`; admin and consumer inherit
  `KaskadeApp.CSS_PATH`. Put main-table borders, titles, subtitles, and loading
  state on `TableFrame`.
- Both root screens use the shared one-line header: version on the left and only
  Kafka `bootstrap.servers` on the right. Preserve semantic contrast, truncate
  Kafka text before the version, use one row of panel padding, and leave one
  column around the root view.
- Deliver record JSON through Textual's file-delivery API from both the table and
  Record Details. Expose Export in Help and Commands, not the Footer.
- Use Title Case for visible titles, headings, tabs, commands, and field labels.
  Toasts authored by Kaskade are concise and omit final periods; binding
  tooltips and CLI diagnostics remain sentences.
- Centered modals have one outer border, `$surface`, semantic colors, constrained
  width, and a compact Footer. The command palette and forms use width `72`
  capped at `90%`; smaller selectors may be narrower.
- Below 80 columns, use Textual's `-narrow` breakpoint: modals and the palette
  fill available width, and Help fills the screen.
- For tabbed modals, border and title the outer `TabbedContent`; inner tables
  remain borderless. Put counts in tab labels such as `Partitions [50]`.
- Table backgrounds are transparent. Primary tables keep focus-aware borders;
  nested detail tables use `details-table`.
- `eva01` is the default custom theme; retain every Textual built-in theme.
  Style CSS with semantic variables and Rich renderables with semantic names,
  never Eva01 hex values.
- `KaskadeApp` synchronizes Rich semantic colors from the active theme and on
  theme changes. Strip `ansi_` before passing Textual ANSI tokens to Rich. Use
  Textual's nested theme provider rather than registering another one.
- Verify visual work with Eva01, a light theme, and an ANSI theme. Keep theme,
  responsive layout, modal, border, and Footer behavior covered in
  `tests/unit/tests_themes.py`.

## Verification and Repository Structure

Run the relevant focused tests plus:

```text
uv run --locked python -m scripts.analyze
uv run --locked python -m scripts.tests
```

Add focused keymap or theme assertions when changing those conventions. Unit
fixtures live in `tests/unit`; E2E tests live in `tests/e2e`, use Confluent Kafka
and Schema Registry through Testcontainers, and should rely on conditions and
public Textual APIs rather than sleeps or private widget state.

README SVGs in `images/` come from `uv run python -m scripts.banner` and
`uv run python -m scripts.screenshots`; neither needs Kafka. Use absolute
`raw.githubusercontent.com` URLs targeting `main`. Paired screenshots use equal
50% table columns and 100% image width.

Keep the manual Kafka environment self-contained in `sandbox`; never share its
fixtures or models with tests. Maintain one topology with three Confluent Kafka
brokers, Apicurio Registry, and Confluent Schema Registry, without a web UI.
The `errors` topic covers valid and malformed Registry payloads plus invalid
UTF-8 headers. Keep topic registration lambda-free through named
`Populator.populate_*` entrypoints.

Reusable script logic belongs in `scripts/__init__.py`; executable modules stay
focused on workflows.

## Releases, Commits, and Pull Requests

- Tags matching `vMAJOR.MINOR.PATCH` on `main` are the only release-version
  source. Hatchling and hatch-vcs derive metadata; never add a static version.
- GitHub Releases are the changelog. Do not add a maintained changelog or
  version-bump commit, and do not hard-code the current version in documentation
  or release commands. Use `kaskade --version`, `MAJOR.MINOR.PATCH`, or Git
  metadata.
- The protected release workflow builds once, verifies the tag, and publishes
  those artifacts to PyPI and GitHub after approval.
- Use Conventional Commits for commit and PR titles, with short imperative
  descriptions. Release notes derive from squash titles; use accurate user-facing
  types such as `feat`, `fix`, `perf`, `docs`, `fix(security)`, and dependency
  `build(deps)` or `chore(deps)`.
- End commit messages and PR descriptions with
  `Assisted-by: <AI model> <version>` after a blank line, using the actual model.
