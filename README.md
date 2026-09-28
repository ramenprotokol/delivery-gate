# delivery-gate

[![CI](https://github.com/ramenprotokol/delivery-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/ramenprotokol/delivery-gate/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python CLI that gives a hard **GO / NO-GO** on a software release. It auto-verifies machine-checkable items and requires a human-attested manifest for everything that needs judgment.

## What it looks like

```text
$ delivery-gate check --repo tests/fixtures/fail_repo --ci-status failure
```

```
delivery-gate report
========================================
[AUTO]      PASS  CHANGELOG updated for this version — Found an entry for 0.1.0.
[AUTO]      FAIL  Tests passed in CI — CI status is 'failure', not 'success'.
[AUTO]      PASS  Dependencies pinned to exact versions — All 1 dependencies are pinned.
[AUTO]      FAIL  Clean, tagged release point — working tree has uncommitted changes
[ATTESTED]  FAIL  Rollback procedure tested — Attested as not done (answer: false).
[ATTESTED]  PASS  On-call engineer notified — Attested by Eng.
[ATTESTED]  PASS  Named approver signed off — Attested by Boss.
[ATTESTED]  PASS  Monitoring and alerts reviewed — Attested by Eng.

Hold reasons (NO-GO):
  - Tests passed in CI: CI status is 'failure', not 'success'.
  - Clean, tagged release point: working tree has uncommitted changes
  - Rollback procedure tested: Attested as not done (answer: false).

Decision: NO-GO
```

Exit code is `1` (NO-GO).

## Why

Shipping mistakes happen when "are we ready?" is answered by memory and optimism instead of a checklist someone can be held to. `delivery-gate` forces you to write down the answers and machine-checks the parts it can prove.

## Install

```bash
pip install -e .
```

Requires Python 3.11+.

> **Not yet on PyPI.** The `pip install -e .` from-source path above is the way to try it today.

## Usage

```bash
delivery-gate check --repo . --ci-status success
```

Want to see it block a release? `delivery-gate check --repo tests/fixtures/fail_repo --ci-status failure`

Exits `0` on GO, `1` on NO-GO, `2` on a manifest or usage error.

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--repo PATH` | `.` | Path to the repository root |
| `--ci-status STATUS` | `$DELIVERY_GATE_CI_STATUS` | CI outcome string, e.g. `success` |
| `--json` | off | Emit JSON instead of human-readable text |

### GitHub Actions example (workflow step)

```yaml
- name: Release gate
  run: delivery-gate check --repo . --ci-status ${{ job.status }}
```

## The checks

### AUTO checks (machine-proven)

These are verified by reading files or injected CI data. `delivery-gate` only claims PASS when it has actually checked.

| ID | What it verifies |
|----|-----------------|
| `changelog` | `CHANGELOG.md` contains the release version string |
| `ci_status` | CI reported `success` (injected via `--ci-status`) |
| `deps_pinned` | Every `pyproject.toml` dependency uses `==` pinning |
| `release_point` | Working tree is clean AND a git tag at HEAD matches the version |

### ATTESTED checks (human-claimed)

These require a person to write down what they did in `release.yaml`. `delivery-gate` reads the file and checks that `answer: true` and a named attester (`by:`) are present. It does **not** verify the claim is true — that is on the human. Results are labeled `[ATTESTED]` in the report.

| ID | What it asks |
|----|-------------|
| `rollback_tested` | Rollback procedure was tested |
| `oncall_notified` | On-call engineer was notified |
| `approver_signed_off` | A named approver signed off |
| `monitoring_reviewed` | Monitoring and alerts were reviewed |

## release.yaml format

Create `release.yaml` at your repo root before running the gate:

```yaml
version: "1.2.3"          # must match version in pyproject.toml / manifest

attestations:
  rollback_tested:
    answer: true
    by: "Jane Smith"
    evidence: "https://ci.example.com/jobs/456"   # optional

  oncall_notified:
    answer: true
    by: "Jane Smith"

  approver_signed_off:
    answer: true
    by: "Bob Lee"

  monitoring_reviewed:
    answer: true
    by: "Jane Smith"

not_applicable:
  feature_flags: "No feature flags in this release."
```

`answer` must be an unquoted YAML boolean (`true` or `false`). A quoted `"false"` or any other
value is rejected with exit code `2`, so it can never be read as a yes. A blank `by:` counts as
no attester.

Keys listed under `not_applicable` skip that check with `NA` status; `NA` does not block GO.

## Prior art & where this fits

| Tool | What it does | How delivery-gate differs |
|------|-------------|--------------------------|
| release-please / semantic-release | Automates release PRs and version bumps | They *perform* releases; delivery-gate *blocks* them until the checklist is satisfied |
| conftest / OPA | General-purpose policy engine | delivery-gate is a focused release checklist with first-class support for human attestation alongside machine checks |
| Danger | Checks code style, PR hygiene at PR time | Danger runs on pull requests and checks code; delivery-gate runs at release time and includes non-code human attestations |
| pre-commit | Runs hooks at commit time | pre-commit is commit-time and local; delivery-gate is release-time, produces an auditable GO/NO-GO record, and can run in CI |

The distinctive idea is the **AUTO vs ATTESTED** honesty model: every result is labeled with whether the tool actually verified the claim or whether a human declared it. Nothing is quietly inferred.

## Honesty note

Every result in the report is labeled either **AUTO** (the tool verified it directly) or **ATTESTED** (a human claimed it in `release.yaml`). The tool never upgrades an attestation to AUTO — you always know what was machine-checked and what was trusted.

## License

MIT. See `LICENSE`.
