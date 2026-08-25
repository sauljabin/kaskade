# Agent Instructions

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
