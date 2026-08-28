<!--
Use a Conventional Commit title such as `feat(admin): add topic search` or
`fix(consumer): handle empty records`. The squash commit title becomes a
release-note entry, so describe one clear outcome in imperative mood.
-->

## Summary

<!-- Explain the problem, motivation, and resulting behavior. -->

Closes #

## Verification

<!-- List the automated and manual checks performed. -->

- [ ] `uv run --locked python -m scripts.analyze`
- [ ] `uv run --locked python -m scripts.tests`
- [ ] Relevant manual or end-to-end checks

## User-facing changes

<!-- Include screenshots for visual changes and describe compatibility or breaking changes. Write "None" when not applicable. -->

## Checklist

- [ ] Tests cover the changed behavior.
- [ ] Documentation and examples reflect the change.
- [ ] No secrets or private infrastructure details are included.
- [ ] The title follows Conventional Commits and is suitable for release notes.

<!-- Replace the values below with the actual assisting model and version. -->
Assisted-by: <AI model> <version>
