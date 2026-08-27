# Agent Instructions

## Code Quality

- Keep cyclomatic complexity at or below 10. The repository-wide Ruff `C901`
  check is part of `scripts.analyze`; prefer focused named helpers over lint
  suppressions.

## Living Knowledge and Documentation

- Treat this file as the project's living operational knowledge. Update it when
  work establishes a durable convention, architectural decision, workflow, or
  constraint that future agents need to follow.
- Review existing guidance while updating it. Remove or rewrite knowledge that
  is obsolete, redundant, contradicted by the implementation, or no longer
  useful; do not only append new sections.
- Apply the same rule to all repository documentation and examples. Whenever a
  change affects documented behavior, commands, configuration, screenshots, or
  workflows, update every relevant document in the same change and remove stale
  information.
- Keep guidance concise and factual. Document stable project knowledge rather
  than temporary implementation details or a chronological history of changes.

## Supported Platforms

- Kaskade must work consistently on Linux and macOS. Keep paths, terminal key
  handling, and shell-facing documentation portable across both platforms.

## Configuration Files

Kaskade has two intentionally separate configuration formats:

- `--config-file kafka.properties` loads Kafka client properties in
  `property=value` format. The CLI `-b/--bootstrap-servers` value supplies
  `bootstrap.servers`, and individual `--config property=value` options override
  values loaded from the properties file. Keep `examples/kafka.properties`
  current when Kafka configuration behavior changes.
- `~/.config/kaskade/config.yaml` configures Kaskade itself. Respect
  `KASKADE_CONFIG` first, then `XDG_CONFIG_HOME`, and finally fall back to
  `~/.config/kaskade/config.yaml` on Linux and macOS. Keep
  `examples/config.yaml` current when configurable bindings change.

Missing, empty, malformed, or partially invalid Kaskade configuration must not
make startup fragile. Ignore invalid entries, retain valid entries, and surface
warnings in the application.

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
- Keep the shared one-line root header on both main applications: show the
  Kaskade version on the left and only Kafka `bootstrap.servers` on the right.
  Truncate the Kafka text before allowing the version to disappear. Leave one
  row around the header and one column on each side of the complete root view.
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
- Tables used as primary screens retain Kaskade's focus-aware border. Detail
  tables embedded inside another bordered component use the borderless
  `details-table` style.

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
  `tests/tests_themes.py`.

## Verification

For TUI, keymap, layout, or theme changes, run:

```text
poetry run python -m scripts.analyze
poetry run python -m scripts.tests
```

Add focused assertions to `tests/tests_themes.py` and/or
`tests/tests_keymaps.py` when changing the conventions above.

## Commits

Use the [Conventional Commits](https://www.conventionalcommits.org/) format for every commit message:

```text
<type>(<optional scope>): <description>
```

The description must be a short, imperative summary of the feature or fix. Do not use it as a list of changes.

End every commit message with an `Assisted-by` trailer, separated from the body by a blank line:

```text
Assisted-by: <AI model> <version>
```

Use the actual AI model and version that generated the commit.

## Pull Requests

Pull request titles and descriptions must follow the same rules as commit messages: use the Conventional Commits format, provide a short imperative summary of the feature or fix rather than a list of changes, and end with the `Assisted-by: <AI model> <version>` trailer.
