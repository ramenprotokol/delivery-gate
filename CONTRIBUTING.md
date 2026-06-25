# Contributing

Thanks for taking a look. This project aims to stay small, honest, and auditable.

## Setup

```bash
git clone https://github.com/ramenprotokol/delivery-gate.git
cd delivery-gate
pip install -e ".[dev]"
pytest
```

## Ground rules

- **Add a test with every change.** Bug fix → a test that fails before, passes
  after. New feature → tests that cover the new behavior.
- **AUTO vs ATTESTED is a hard line.** A check labeled `AUTO` must machine-verify
  what it claims. A check labeled `ATTESTED` reads a human declaration and trusts
  it. Never silently upgrade an attestation to AUTO — the whole point of the label
  is that users know what the tool actually checked vs. what it took on faith.
- **Tests run offline.** No network calls, no external services. The test suite
  must pass with no internet access.
- **Ruff must be clean.** Run `ruff check .` and `ruff format --check .` before
  opening a PR. Use `ruff format .` and `ruff check --fix .` to auto-fix most
  issues.

## Adding a new check

1. Create a module in `src/delivery_gate/checks/` that defines a class
   implementing the `Check` interface from `src/delivery_gate/base.py`.
2. Set `id`, `label`, and `kind` on the class. Use `Kind.AUTO` only if the check
   genuinely machine-verifies the claim. Use `Kind.ATTESTED` if it reads a human
   declaration from `release.yaml`.
3. Register the check in `src/delivery_gate/runner.py` alongside the existing
   checks.
4. Add tests covering PASS, FAIL, and NA paths for the new check.

## Before opening a PR

```bash
pytest -q                   # all green
ruff check .                # no lint errors
ruff format --check .       # no format issues
delivery-gate --help        # CLI still imports cleanly
```
