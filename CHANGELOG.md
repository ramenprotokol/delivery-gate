# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]

### Security

- CI workflow runs with a read-only `GITHUB_TOKEN` (`permissions: contents: read`).
- Dev dependency `pytest` bumped from 8.3.3 to 9.1.1 (CVE-2025-71176, predictable
  `/tmp/pytest-of-{user}` directories; dev/test only, not a runtime dependency).

### Fixed

- A `release.yaml` that nests too deeply, uses more than 100 aliases (`*name`), or whose
  merge keys (`<<`) grow one mapping past 1,000 entries, is now a manifest error (exit 2).
  Merge keys are expanded while the file loads, before any field is checked, so a ~700-byte
  chain took 9 s and 760 MB and each extra level multiplied that by nine, and a ~110 KB file
  merging one large mapping 20,000 times built a ~350 MB list. Deep nesting crashed with a
  traceback (exit 1).
- `evidence` in an attestation must be text, matching its declared type. A YAML
  alias chain there was expanded into the report (383 bytes of YAML became ~3.8 MB
  of output, and a few more levels exhaust memory).
- `deps_pinned` no longer counts an `==` inside an environment marker
  (`pywin32; sys_platform == 'win32'`) or a `==1.*` wildcard as a pin. It now fails
  instead of passing when `pyproject.toml` has no `[project]` table (for example
  Poetry) or declares `dependencies` as `dynamic`, since nothing was checked.
- The `changelog` check now needs a Markdown heading that names the exact version
  (`## [1.2.3]`, `## v1.2.3`, ...). It used a plain substring search, so the version
  anywhere in the file passed, including prose like "no 0.1.0 entry", a link
  reference, or a longer version (`1.0` matched `1.0.5`).
- `version` in `release.yaml` must be a quoted string (unquoted `1.10` loaded as
  the float `1.1`), and each `not_applicable` entry needs a non-empty written reason
  (`rollback_tested: false` under `not_applicable` used to skip the check).
- A quoted or non-boolean `answer` in `release.yaml` (for example `answer: "false"`)
  is now a manifest error (exit 2). Before, any non-empty string counted as `true`,
  so `answer: "false"` passed as attested. A whitespace-only `by:` now counts as no
  attester.
- `release_point` now fails closed when a git command errors. Before, a failed
  `git status` (for example a corrupt index) was read as "clean", so a dirty,
  tagged tree could get a GO.

## 0.1.0 - 2026-06-24

First release of `delivery-gate`.

### Added

- Core check interface: `Status`, `Kind`, `Result`, `Check`, `Context` in `base.py`
- Release manifest model and YAML loader (`release.yaml` with `version`, `attestations`, `not_applicable`)
- Injectable `GitAdapter` for `is_clean()` and `tag_at_head()` — no network required in tests
- Four AUTO checks: `changelog` (CHANGELOG.md entry), `ci_status` (injected CI outcome), `deps_pinned` (exact `==` pins in pyproject.toml), `release_point` (clean tree + matching tag)
- Four ATTESTED checks: `rollback_tested`, `oncall_notified`, `approver_signed_off`, `monitoring_reviewed`
- Runner that assembles all checks, runs them, and returns a GO/NO-GO decision
- Text and JSON reporters — every result labeled `[AUTO]` or `[ATTESTED]`
- CLI entrypoint `delivery-gate check` with `--repo`, `--ci-status`, `--json`; exits `0` (GO), `1` (NO-GO), `2` (manifest/usage error)
- Full unit test suite covering PASS / FAIL / NA paths per check, plus end-to-end fixture tests
