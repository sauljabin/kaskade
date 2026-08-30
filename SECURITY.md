# Security Policy

## Supported versions

Security fixes are provided for the latest stable Kaskade release. Users should
upgrade to the newest release before reporting an issue that may already be
fixed.

| Version | Supported |
| --- | --- |
| Latest stable release | Yes |
| Older releases | No |
| `main` development branch | Best effort; not a supported release |

## Reporting a vulnerability

Do not report suspected vulnerabilities in a public issue, discussion, pull
request, log, or screenshot.

Use [GitHub private vulnerability reporting](https://github.com/sauljabin/kaskade/security/advisories/new)
whenever possible. If that form is unavailable, email
`sauljabin@gmail.com` with the subject `[Kaskade security]` and include only the
minimum sensitive detail needed to establish contact.

Include the following when it is safe to do so:

- The affected Kaskade version or commit.
- Operating system, Python version, installation method, and Kafka distribution.
- A concise description of the vulnerability and its likely impact.
- Reproduction steps or a minimal proof of concept using test data.
- Whether credentials, private broker details, or production data may have been
  exposed.
- Any known mitigations and your preferred name for advisory credit.

Never send real passwords, tokens, private keys, certificates, production
records, or private infrastructure details. Replace them with synthetic values.

Security-sensitive examples include credential or configuration disclosure,
unsafe file handling, command execution, authorization-boundary mistakes, and
dependency vulnerabilities with a demonstrated impact on Kaskade.

## Handling and disclosure

The maintainer will assess the report, request missing information when needed,
and keep confirmed vulnerabilities private while a fix is prepared. Resolution
time depends on severity, complexity, and maintainer availability; reporters
will receive material status updates through the private report.

Please allow time for investigation and remediation before publishing details.
The maintainer and reporter should coordinate disclosure, release, advisory,
and credit timing. Confirmed vulnerabilities may be published as GitHub
repository security advisories after a fixed release is available.

Questions, troubleshooting, hardening suggestions without a concrete security
impact, and ordinary bugs belong in GitHub Discussions or the public issue
tracker after all sensitive information has been removed.
