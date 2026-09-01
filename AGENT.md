# Agent Instructions

## Code Quality

- Keep cyclomatic complexity at or below 10. The repository-wide Ruff `C901`
  check is part of `scripts.analyze`; prefer focused named helpers over lint
  suppressions.
- Before considering implementation complete, perform a final refactor review
  of the entire diff for readability and maintainability. Remove duplicated
  literals and branches, extract focused helpers where they clarify intent, and
  rerun the relevant analysis and tests after any cleanup.

## Living Knowledge and Documentation

- Treat this file as living operational knowledge. Record durable conventions,
  and remove obsolete, redundant, or contradicted guidance instead of only
  appending. Apply the same rule to all affected documentation and examples.
- Keep guidance concise and factual. Document stable project knowledge rather
  than temporary implementation details or a chronological history of changes.

## Supported Platforms

- Kaskade must work consistently on Linux and macOS. Keep paths, terminal key
  handling, and shell-facing documentation portable across both platforms.

## CLI and Configuration

- Keep the admin and consumer Kafka connection declarations shared. Their help
  uses `Kafka connection options`, `AWS options`, and `Application options`;
  consumer additionally separates `Consumption options` from
  `Deserialization options`. Keep `--earliest` and `--partition` declaratively
  mutually exclusive and render the theme argument as `name` without weakening
  choice validation.

Kaskade has two intentionally separate configuration formats:

- `--config-file kafka.properties` loads Kafka client properties in
  `property=value` format. Merge precedence is file properties, repeatable
  `--config property=value` entries, then an optional
  `-b/--bootstrap-servers` override. Require a non-empty resolved
  `bootstrap.servers` before constructing either application. Keep
  `examples/kafka.properties` current when this behavior changes.
- `~/.config/kaskade/config.yaml` configures Kaskade itself. Respect
  `KASKADE_CONFIG` first, then `XDG_CONFIG_HOME`, and finally fall back to
  `~/.config/kaskade/config.yaml` on Linux and macOS. Keep
  `examples/config.yaml` current when configurable bindings change.

Missing, empty, malformed, or partially invalid Kaskade YAML configuration must
not make startup fragile. Ignore invalid entries, retain valid entries, and
surface warnings in the application.

Amazon MSK IAM authentication is enabled with `--aws region=<region>` in admin,
consumer, and the sandbox population tool. Keep AWS-specific CLI settings in
the repeatable `--aws property=value` form and validate them before constructing
Kafka clients. The signer dependency baseline is
`aws-msk-iam-sasl-signer-python>=1.0`; do not raise its minimum version without
requiring newer functionality.

## Runtime Initialization

- Importing `kaskade` must not create directories, open files, or modify the root
  logger. Configure the named Kaskade logger lazily from the CLI and tolerate an
  unavailable log destination.
- Local-schema Avro payloads use raw framing by default. Confluent's five-byte
  framing must be selected explicitly with `--avro framing=confluent`; do not
  infer it from the first byte because valid raw Avro may begin with zero.

## Admin Data Loading

- Render topic metadata before loading record and consumer-group metrics.
- Fetch partition offsets with batched Admin API requests and consumer-group
  offsets with bounded concurrency; do not create temporary consumers for admin
  metrics.
- Keep the last complete metrics visible during refreshes and never overlap
  automatic, manual, resumed, or post-mutation refresh work.
- Coalesce non-periodic refresh requests behind active work and keep refresh
  state transitions in the shared coordinator rather than adding independent
  flags to the topic list.
- Admin auto-refresh defaults to 30 seconds, pauses while another screen is
  open, and is configured with `admin.refresh_interval_seconds` in Kaskade's
  YAML configuration or overridden per session with `admin --refresh-interval`.
  A value of `0` disables it.

## Consumer Positioning and Deserialization

- `consumer --earliest` subscribes to every topic partition with
  `auto.offset.reset=earliest`. Repeatable `--partition
  PARTITION[:OFFSET|earliest]` selections instead use manual assignment and must
  never fetch unlisted partitions. Numeric offsets are absolute, including `0`.
- Treat recognized key and value deserialization failures independently per
  record. Cache a BYTES fallback with warning metadata, keep the configured
  deserializer for subsequent records, and preserve the diagnostics in details,
  cell tooltips, copy, and export. Broker failures and unexpected exceptions
  remain fatal.

## TUI Interaction Conventions

Kaskade follows familiar k9s/Vim-style terminal interactions where practical:

- Preserve arrow-key navigation and the Vim alternatives `h`, `j`, `k`, and
  `l`. Use `g`/`G` for first/last navigation where applicable.
- Keep shortcuts safe for common terminal multiplexers such as tmux and Zellij.
  Quit is `ctrl+c` only; do not add `ctrl+q`.
- Use stable binding IDs so users can override shortcuts through Kaskade's YAML
  keymap. Every Kaskade binding ID must be represented in `KNOWN_BINDING_IDS`.
- Every visible binding needs a concise Title Case description and a useful
  tooltip. Add the corresponding example configuration and tests when adding or
  renaming a binding.
- Plain-character shortcuts must not intercept typing in inputs. In particular,
  `?` opens Help in normal contexts while `f1` remains available from a focused
  text input.
- Contextual entity copy uses `y` and Textual's best-effort OSC 52 clipboard
  API. Keep it hidden from the Footer but available in Help and Commands. Keep
  the compatibility matrix in `USAGE.md` authoritative and link to it rather
  than duplicating it. Selected-text copy uses `Cmd+C` on macOS or
  `Ctrl+Shift+C` on Linux; `Ctrl+C` always quits and is never a copy alias.
- Keep Textual's command palette on `:` with `ctrl+p` as an alternative. Expose
  contextual Kaskade actions in it, omit duplicate navigation actions, and do
  not expose Textual maximize/minimize commands. Replace Textual's generic Keys
  command with Kaskade's contextual Help window.

### Footer command order

Binding declaration order controls Textual's Footer order. Preserve this order:

- Main screens: contextual actions, then `Quit`, `Help`, and `Commands`.
- Action modals: primary action, then `Back` or `Cancel`, then `Help`.
- Read-only modals: `Back`, then `Help`.
- Help: `Back` only, displayed as `esc Back`.

Use `modal_bindings(...)` for regular modals so the shared Help binding is
appended last. Do not put Help on the base modal class: Textual merges inherited
bindings first, which moves Help ahead of contextual actions. Show implicit
submit keys such as Enter in the Footer whenever they perform the modal's
primary action.

## Help Window

Help is a dedicated centered `ModalScreen`, not a sidebar. It must:

- Snapshot the bindings of the screen beneath it and group them by context.
- Show every effective shortcut alias for each action while leaving compact
  Footer key displays unchanged.
- Put keyboard focus on its command table so arrows and page navigation work
  without a mouse, then restore the previous focus when it closes.
- Use the contextual border title `Help — <Context>`.
- Show the application name and version at the top, followed by the About
  section, project URL, and issue-reporting URL, with spacing before the command
  table.
- Show the standard compact Footer with only `esc Back`; do not replace the
  Footer with custom navigation instructions.
- Let `?`, `f1`, and `q` close the window without displaying duplicate Footer
  commands.

## Layout, Modals, and CSS

- Keep all application styling in the shared `kaskade/styles.css`; both admin
  and consumer applications inherit `KaskadeApp.CSS_PATH`.
- Keep main-table borders, titles, and subtitles on the shared `TableFrame` so
  a table's loading indicator replaces only its content inside the frame.
- Keep the shared one-line root header on both main applications: show the
  Kaskade version on the left and only Kafka `bootstrap.servers` on the right.
  Give the name and version contrasting semantic colors, and truncate the Kafka
  text before allowing the version to disappear. Pad the header by one row in
  the shared panel background and leave one column on each side of the complete
  root view.
- Deliver consumed-record JSON exports through Textual's file-delivery API so
  they use the same Downloads or browser destination as screenshots. Keep the
  export available from both the records table and Record Details, expose it in
  Help and Commands, and keep it hidden from the Footer.
- Use Title Case for screen titles, border titles, table headings, tabs, command
  labels, and field labels.
- Follow the existing centered-modal vocabulary: one visible outer border,
  `$surface` background, semantic theme colors, constrained width, and a compact
  Footer. Avoid full-terminal modal widths on wide screens.
- Keep the command palette at width `72`, capped at `90%`. Forms use the same
  width convention; smaller selectors may use narrower fixed widths.
- Use Textual's `-narrow` breakpoint below 80 columns. On narrow terminals,
  modals and the command palette expand to the available width, and Help expands
  to the full screen.
- When a modal contains tabs, put the modal border and contextual title on the
  outer `TabbedContent`. Do not add borders or border titles to the tables inside
  the tabs. Put collection counts in tab labels, for example
  `Partitions [50]`.
- Keep table backgrounds transparent so they inherit each window's background.
  Primary tables retain Kaskade's visible focus-aware border, while detail
  tables embedded inside another bordered component use the borderless
  `details-table` style.
- Keep toast notification text concise and omit trailing periods. This applies
  to informational, warning, and error messages authored by Kaskade; binding
  tooltips and CLI diagnostics remain complete sentences.

## Themes

- `eva01` is Kaskade's custom default Textual theme. Keep all Textual built-in
  themes available alongside it through `available_theme_names()` and the
  `--theme` option on both admin and consumer commands.
- Style widgets with Textual semantic variables such as `$primary`,
  `$secondary`, `$surface`, and `$text-muted`; do not couple CSS to Eva01's raw
  hex values. Changes must remain legible in dark, light, and ANSI themes.
- Rich renderables must use semantic names such as `primary`, `secondary`,
  `warning`, `error`, `success`, and `accent`. `KaskadeApp` synchronizes those
  names from the active Textual theme and must resynchronize on runtime theme
  changes.
- Preserve ANSI compatibility when translating Textual colors to Rich colors.
  Textual `ansi_*` tokens need their prefix removed before Rich consumes them.
- Use Textual's built-in nested theme provider in the command palette; do not
  register a duplicate `ThemeProvider` in the app's command providers.
- Verify visual/theme work against the custom default, at least one Textual
  light theme, and an ANSI theme. Keep the Rich synchronization, shared CSS,
  responsive breakpoint, modal geometry, borders, and Footer order covered by
  `tests/unit/tests_themes.py`.

## Verification

README visual assets are generated as SVG files in `images/` with Textual's
screenshot exporter. Run `uv run python -m scripts.banner` for the banner and
`uv run python -m scripts.screenshots` for the mock-data admin and consumer
views; neither command requires a Kafka broker. README image sources must use
absolute `raw.githubusercontent.com` URLs targeting the `main` branch so they
render in published package metadata. Keep paired screenshots in equal 50%
table columns with each image at 100% width so GitHub renders them at the same
size.

For TUI, keymap, layout, or theme changes, run:

```text
uv run --locked python -m scripts.analyze
uv run --locked python -m scripts.tests
```

Add focused assertions to `tests/unit/tests_themes.py` and/or
`tests/unit/tests_keymaps.py` when changing the conventions above.

Unit tests and their Avro, JSON Schema, and Protobuf fixtures live in
`tests/unit`. End-to-end tests live in `tests/e2e` and use Confluent Kafka
through Testcontainers. Keep E2E tests condition-based and use public Textual
APIs rather than fixed sleeps or private widget state.

The manual Kafka environment lives entirely in `sandbox`, including its own
schema models, generated Protobuf artifacts, Compose file, and environment
versions. Never import test fixtures from sandbox utilities or sandbox models
from tests. Its `errors` topic cycles through valid and deliberately malformed
Schema Registry key/value payloads for consumer fallback testing. Keep one
Compose topology: three Confluent Kafka brokers, Apicurio Registry, and
Confluent Schema Registry, with no web UI.

Reusable script classes and functions belong in `scripts/__init__.py`; keep
individual script modules focused on executable workflows.

## Releases and Versions

- Git tags matching `vMAJOR.MINOR.PATCH` are the only release-version source.
  Hatchling and hatch-vcs derive package metadata from Git; never add or edit a
  static package version.
- GitHub Releases are the canonical changelog. Do not add a maintained changelog
  file or a version-bump commit.
- Never hard-code Kaskade's current release version in documentation, issue
  templates, examples, or release commands. Refer to `kaskade --version`, use a
  `MAJOR.MINOR.PATCH` placeholder, or derive the version from Git metadata so a
  release does not require follow-up file edits.
- Release tags must point to commits on `main`. The protected release workflow
  builds once, verifies the tag against the artifacts, and publishes those same
  artifacts to PyPI and GitHub after approval.
- Release notes are generated from squash commit titles. Keep pull request titles
  and commits in Conventional Commits format and describe user-visible outcomes
  with `feat`, `fix`, `perf`, `docs`, `fix(security)`, or dependency-scoped
  `build(deps)`/`chore(deps)` types where applicable.

## Commits and Pull Requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
  messages and pull request titles. Use a short, imperative description rather
  than a list of changes.
- End commit messages and pull request descriptions with
  `Assisted-by: <AI model> <version>`, separated from the body by a blank line.
  Use the actual model and version that generated the change.
