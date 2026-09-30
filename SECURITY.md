# Security Policy

## Supported versions

Security fixes go into the latest stable release. Please upgrade to it before
reporting something that may already be fixed.

| Version | Supported |
| --- | --- |
| Latest stable release | Yes |
| Older releases | No |
| `main` development branch | Best effort; not a supported release |

## Reporting a vulnerability

Don't report suspected vulnerabilities in a public issue, discussion, pull
request, log, or screenshot.

Use [GitHub private vulnerability reporting](https://github.com/sauljabin/kaskade/security/advisories/new)
if you can. If that form isn't available, email `sauljabin@gmail.com` with the
subject `[Kaskade security]`, and include only as much sensitive detail as it
takes to get in touch.

When it's safe to include them, these help:

- The affected Kaskade version or commit.
- Operating system, Python version, installation method, and Kafka distribution.
- A short description of the vulnerability and its likely impact.
- Steps to reproduce it, or a minimal proof of concept that uses test data.
- Whether credentials, private broker details, or production data may have been
  exposed.
- Any mitigations you know of, and the name you'd like credited in the
  advisory.

Never send real passwords, tokens, private keys, certificates, production
records, or private infrastructure details. Replace them with made-up values.

Examples of security bugs: credentials or configuration leaking, unsafe file
handling, command execution, authorization-boundary mistakes, and dependency
vulnerabilities with a demonstrated impact on Kaskade.

## Handling and disclosure

The maintainer will assess the report, ask for anything missing, and keep a
confirmed vulnerability private while a fix is prepared. How long that takes
depends on severity, complexity, and the maintainer's availability; you'll get
status updates through the private report when something changes.

Please allow time for investigation and a fix before publishing details. The
maintainer and the reporter should agree on the timing of disclosure, the
release, the advisory, and credit. Confirmed vulnerabilities may be published
as GitHub security advisories once a fixed release is available.

Questions, troubleshooting, hardening ideas without a concrete security impact,
and ordinary bugs go in GitHub Discussions or the issue tracker, with anything
sensitive removed.
