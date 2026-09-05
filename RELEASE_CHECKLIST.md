# AI Agent Release Checklist

Use this checklist for every release. Complete the shared preparation checks,
the section for the selected release type, then publishing, verification, and
announcements. Major releases require a comprehensive review; minor and patch
releases narrow the review without relaxing the shared quality checks.

Keep this file reusable and unchecked. Record release-specific results in the
agent's task report: candidate version and commit, evidence or command results,
failures, justified exceptions, unavailable checks, and announcement drafts.
Mark a check complete only when verified; record non-applicable items with a
reason. Resolve blockers before publishing and do not report readiness while
required checks remain unverified.

This checklist does not authorize tagging or publication. Use existing explicit
release authorization, requesting it only if absent. Announcement submission
requires explicit approval of the prepared draft.

## Shared Preparation — Every Release

- [ ] Record the proposed version, candidate commit, previous release tag, and
  comparison range. Review the complete release diff and Conventional Commit
  history, not just changes from the current task.
- [ ] Confirm the version classification, backward compatibility, known issues,
  and relevant security advisories. Identify breaking changes and required
  migration guidance before choosing the release type.
- [ ] Verify lockfile consistency, code analysis, unit tests, and E2E tests using
  the workflows in [Development](DEVELOPMENT.md#scripts). E2E tests require
  Docker; record an unavailable environment rather than claiming a pass.
- [ ] Confirm successful [CI](.github/workflows/main.yml) for the final candidate,
  including the supported Python and Linux/macOS matrix, packaging, and E2E
  jobs. Refresh evidence for changes made during release preparation.
- [ ] Build and verify the wheel and source distribution using
  [Build Artifacts](DEVELOPMENT.md#build-artifacts). Install the wheel in an
  isolated environment and smoke-test `kaskade --version`,
  `kaskade admin --help`, and `kaskade consumer --help`. An untagged candidate
  has a development version; the release workflow verifies the exact tag version.
- [ ] Review release-note coverage against the comparison range, including
  user-facing fixes, features, breaking changes, and known limitations. Keep
  GitHub Releases as the canonical changelog; do not add a maintained changelog
  or a static version field.

## Major Release — Comprehensive Review

- [ ] Review all documentation for accuracy, outdated or contradictory guidance,
  broken links, and duplication. Keep detailed instructions in their canonical
  document and link to them, following [Agent Instructions](AGENT.md#engineering-and-documentation).
- [ ] Update [README](README.md) capabilities, installation instructions,
  examples, and screenshots to reflect the release.
- [ ] Update and [preview the website](DEVELOPMENT.md#website). Check alignment
  with the README, generated assets, links, responsive layout, and runtime
  latest-release lookup and fallback. Do not hard-code the current release tag.
- [ ] Review Python runtime dependencies, build and development tools, GitHub
  Actions, pre-commit hooks, and container images against their latest stable
  releases, including major upgrades. Update dependencies and the lockfile,
  apply required adaptations, and document unresolved upgrade blockers.
- [ ] Explicitly review dependency-related Python, operating-system, and service
  compatibility changes. Document support changes and migrations; do not raise
  minimum dependency versions merely to match the lockfile. Preserve documented
  baselines unless newer functionality requires changing them.
- [ ] Compact `AGENT.md` by removing duplication and obsolete guidance without
  losing unique instructions. Verify every removed instruction is still
  represented or linked, unless it is demonstrably obsolete.
- [ ] Review CLI, configuration, consumer-record schema, and TUI compatibility.
  Document breaking changes and actionable migration steps.
- [ ] Run the documented [sandbox smoke tests](DEVELOPMENT.md#manual-tests),
  including admin, consumer, deserialization, and Registry behavior. Follow
  the agent instructions for theme and responsive-layout verification.

## Minor Release — Focused Feature Review

- [ ] Confirm new functionality is backward compatible. Reclassify breaking
  changes as a major release and use the major checklist.
- [ ] Review and update documentation, README, website, screenshots, and agent
  instructions for affected behavior; avoid an unrelated repository-wide audit.
- [ ] Update dependencies needed for features, fixes, security, or compatibility.
  A wholesale dependency upgrade is not required.
- [ ] Run additional manual and visual checks for changed behavior and its
  integration paths, using the development guide and agent conventions.
- [ ] Review release notes for new features, fixes, and relevant limitations.

## Patch Release — Focused Correction Review

- [ ] Confirm changes are backward-compatible fixes, security corrections, or
  maintenance. Reclassify new features as minor and breaking changes as major,
  then use that release type's checklist.
- [ ] Verify each fix with a focused regression test or a reproducible
  before/after check, recording the evidence.
- [ ] Review affected behavior and nearby integration paths for regressions;
  run focused manual or visual checks where applicable.
- [ ] Correct documentation, README, website, screenshots, and agent instructions
  where the patch makes them inaccurate. Skip broad documentation audits and
  full `AGENT.md` compaction.
- [ ] Limit dependency updates to those required by fixes, security, or
  compatibility; skip wholesale upgrades.
- [ ] Summarize corrected behavior and remaining known issues in release notes.

## Publishing and Post-release Verification

- [ ] Present preparation results, resolve blockers, and confirm release
  authorization before creating or pushing a tag. Follow
  [Release](DEVELOPMENT.md#release) for a clean, current `main`, tag creation,
  publishing configuration, protected approvals, and failure recovery.
- [ ] Follow the [release workflow](.github/workflows/release.yml) through tag
  validation, artifact verification, and protected publishing. Preserve its
  build-once distribution bundle and review generated release notes.
- [ ] Verify the expected version is available on PyPI and installs successfully
  in an isolated environment; check version reporting and both CLI help commands.
- [ ] Verify the versioned and `latest` Docker tags, expected image platforms,
  and version reporting from the published image.
- [ ] Verify the GitHub release tag, downloadable wheel and source distribution,
  release notes, and links match the intended release.
- [ ] Verify the live website's release discovery and relevant deployment status.
  Record Homebrew availability separately; its update may lag publication and
  does not by itself block release completion.
- [ ] If publication fails, follow the development guide's recovery procedure.
  Record partial publication accurately; do not move or reuse release tags or
  replace immutable published artifacts.

## Announcement

- [ ] Determine whether an announcement is required: always for majors; for
  minors with meaningful features, workflow changes, or significant fixes; and
  for patches with significant fixes or security updates. Record the reason
  when no announcement is needed.
- [ ] When required, prepare the complete title and body in the agent's task
  report. Include relevant features, fixes, breaking changes, migration steps,
  known limitations, and release links, supported by the release diff and notes.
- [ ] After release verification, check the
  [Announcements category](https://github.com/sauljabin/kaskade/discussions/categories/announcements)
  for an existing announcement to avoid duplicate submissions.
- [ ] Present the exact draft and obtain explicit approval before submitting it
  to Announcements. Release authorization does not replace announcement approval;
  leave the draft pending until approved.
- [ ] Submit the approved announcement, verify the resulting post, and record
  its link in the task report. If posting is unavailable, retain the approved
  draft and report the blocker rather than claiming submission.
