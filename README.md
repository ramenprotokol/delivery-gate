# delivery-gate

A Python CLI that gives a hard **GO / NO-GO** on a software release. It auto-verifies machine-checkable items and requires a human-attested manifest for everything that needs judgment.

## Why

Shipping mistakes happen when "are we ready?" is answered by memory and optimism instead of a checklist someone can be held to. `delivery-gate` forces you to write down the answers and machine-checks the parts it can prove.

## Install

```bash
pipx install delivery-gate      # once it is on PyPI
# or from source:
pip install -e .
```

Requires Python 3.11+.

## Usage

```bash
delivery-gate check --repo . --ci-status success
```

Exits `0` on GO, `1` on NO-GO, `2` on a manifest or usage error.

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--repo PATH` | `.` | Path to the repository root |
| `--ci-status STATUS` | `$DELIVERY_GATE_CI_STATUS` | CI outcome string, e.g. `success` |
| `--json` | off | Emit JSON instead of human-readable text |

### GitHub Actions example (`release.yaml`)

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

Keys listed under `not_applicable` skip that check with `NA` status; `NA` does not block GO.

## Honesty note

Every result in the report is labeled either **AUTO** (the tool verified it directly) or **ATTESTED** (a human claimed it in `release.yaml`). The tool never upgrades an attestation to AUTO — you always know what was machine-checked and what was trusted.

## License

MIT. See `LICENSE`.
