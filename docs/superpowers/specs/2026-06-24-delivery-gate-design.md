# delivery-gate — Design Spec

- **Date:** 2026-06-24
- **Status:** Approved (brainstorming → ready for implementation plan)
- **Project #4** in the Ramen Protocol public portfolio
- **Through-line:** completes `methodology → measure → enforce`
  (ai-delivery-engineering → hallucination-hunter → **delivery-gate**)

---

## 1. Purpose

A small command-line tool that answers one question before a release ships:
**"Is this release actually safe to go out — GO or NO-GO?"**

It enforces the **Release Readiness Checklist** published in
[`ai-delivery-engineering/checklists/release-readiness.md`](https://github.com/ramenprotokol/ai-delivery-engineering).
The CLI verifies what a machine can verify, makes a human attest to the rest, and
exits with a pass/fail code so a broken release can be **stopped** in CI — not
merely advised against.

### What it is not
- Not a generic rules engine (no user-defined DSL). YAGNI for v0.1.
- Not an interactive wizard. It reads state + a manifest and decides.
- Not tied to any private repo. Generic, public, installable like `hh`.

---

## 2. Core shape (decided)

| Decision | Choice |
|---|---|
| Split machine vs human checks | **Auto-check + attestation file.** Machine proves what it can; human attests to the rest in a manifest. |
| Primary use | **CI gate, exit-code driven.** Blocking step in GitHub Actions. Also runnable locally. |
| Distribution | Generic public OSS Python CLI, `pyproject.toml` + `src/` layout (matches hallucination-hunter house style). |
| Architecture | **Pluggable checks** with one shared interface; separate runner / reporter / CLI. |

---

## 3. How it's used

1. Author drops `release.yaml` at the repo root. It declares the release version,
   marks any "[if applicable]" sections N/A with a reason, and records human
   attestations (each: a statement, true/false, an attester name, optional
   evidence link).
2. Run `delivery-gate check`.
3. The tool prints a report and **exits non-zero on NO-GO** (fails the CI step),
   `0` on GO.

### Example `release.yaml`
```yaml
version: "0.1.0"
attestations:
  rollback_tested:
    answer: true
    by: "A. Engineer"
    evidence: "https://…/staging-dry-run"
  approver_signed_off:
    answer: true
    by: "Release Approver"
  oncall_notified:
    answer: true
    by: "A. Engineer"
not_applicable:
  feature_flags: "No new user-facing feature behind a flag this release."
```

---

## 4. What it checks

### 4.1 Auto-checks (machine-proven, no trust required) — v0.1 scope
1. **CHANGELOG updated** — `CHANGELOG.md` contains an entry matching `version`.
2. **Tests passed in CI** — latest CI run on the gated commit is green
   (GitHub API, or an explicitly passed-in status).
3. **Dependencies pinned** — scan declared deps; flag anything not locked to an
   exact version. **v0.1 targets Python projects** (`pyproject.toml` /
   `requirements.txt`); other ecosystems are future work. Maps to checklist §6.
4. **Clean release point** — no uncommitted changes; on a tagged commit; the git
   tag matches `version` in the manifest.

### 4.2 Attestation checks (human-claimed, manifest-backed)
Every required human-judgment item from the checklist (rollback tested, on-call
notified, approver sign-off, monitoring/alerts reviewed, etc.) must be present in
`release.yaml` and answered `true`. Missing or `false` → NO-GO. Items marked
`not_applicable` with a reason are skipped and recorded as N/A.

> **Honesty principle:** the report always labels each result as
> **machine-proven** vs **human-attested**, so the gate never overclaims.

---

## 5. Architecture

Small, independently testable units with one clear job each.

```
src/delivery_gate/
  cli.py          # arg parsing, exit codes, entrypoint
  manifest.py     # load + validate release.yaml -> typed object; clear errors
  runner.py       # collect checks, run them, aggregate GO/NO-GO
  report.py       # render results (human text + --json)
  checks/
    base.py       # Check interface + Result(status, label, message, kind)
    changelog.py  # auto-check
    ci_status.py  # auto-check
    deps_pinned.py# auto-check
    release_point.py # auto-check (git cleanliness + tag/version match)
    attestation.py# turns manifest attestations into Results
  adapters/
    git.py        # thin git subprocess wrapper
    github.py     # CI status lookup (API / env / passed-in)
```

### Shared check interface
- Every check exposes `run(context) -> Result`.
- `Result` = `{ status: PASS | FAIL | NA, kind: AUTO | ATTESTED, label, message }`.
- Checks know nothing about printing; the **reporter** knows nothing about check
  internals; the **runner** orchestrates. This is what makes each piece testable
  in isolation and new checks cheap to add (pre-merge, security-review later).

### Data flow
`cli` → load `manifest` → build `context` (manifest + git/github adapters) →
`runner` runs all checks → `reporter` renders → `cli` exits `0` (GO) / `1` (NO-GO).

---

## 6. Error handling

- **Bad / missing `release.yaml`** → clear, actionable error (what field, what's
  expected); exit code reserved for usage error, not a crash/traceback.
- **CI status unreachable** → reported honestly and treated as **FAIL** (safe
  default: when unsure, do not ship).
- **NO-GO output** lists **every** failing reason, never just the first.
- Report ends with an explicit `GO` / `NO-GO` line and a hold-reasons block on
  NO-GO, mirroring the checklist's decision table.

---

## 7. Testing

Matches the hallucination-hunter standard (pytest, green CI):
- **Unit:** each check covered for PASS, FAIL, and NA paths.
- **Manifest:** valid parse, each validation error, N/A handling.
- **Adapters:** git wrapper and CI-status lookup with stubbed I/O.
- **End-to-end:** a fixture "should-pass" repo exits 0; a "should-fail" repo
  (e.g. missing changelog entry + a `false` attestation) exits non-zero with all
  reasons listed.
- `--json` output shape is asserted for machine consumers.

---

## 8. Out of scope for v0.1 (future)
- Enforcing the other checklists (pre-merge, security-review) — same check
  interface makes this additive later.
- A generic user-defined rules DSL.
- A polished interactive local walkthrough.

---

## 9. Project conventions

- **Rule 1:** a short project note is written before real work.
- **Rule 2:** run a repository audit and a privacy check before going public.
- Honest demo data; AI co-author commit trailer kept.
