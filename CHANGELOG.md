# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]

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
