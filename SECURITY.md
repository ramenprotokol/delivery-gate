# Security Policy

## Supported versions

The latest commit on the `main` branch is the supported version.

## Reporting a vulnerability

Please report security issues **privately**, not as a public issue.

- Preferred: open a private report via GitHub's
  [Security advisories](https://github.com/ramenprotokol/delivery-gate/security/advisories/new).
- You can expect an initial response within 7 days.

## What this tool does (and does not do)

`delivery-gate` is a local CLI. It does not make network requests, does not
store credentials, and does not transmit data anywhere. It reads:

- `release.yaml` — the human-authored release manifest in your repo
- Your git repository state (working tree cleanliness, tag at HEAD)
- `pyproject.toml` — to check dependency pinning
- `CHANGELOG.md` — to verify the version entry exists

No secrets are required to run `delivery-gate`. If you discover a way the tool
could be tricked into producing a false GO decision (e.g., a path-traversal
issue, a manifest-parsing flaw, or a logic error in a check), please report it
privately so it can be fixed before release.
