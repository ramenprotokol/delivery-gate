# delivery-gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that gives a hard GO/NO-GO on a software release by auto-verifying machine-checkable items and requiring a human-attested manifest for the rest.

**Architecture:** Small, independently testable "checks" sharing one interface (`run(context) -> Result`). A runner collects and aggregates results into a GO/NO-GO; a reporter renders them (text + JSON); the CLI sets the process exit code. Auto-checks read the repo/git/CI; attestation checks read `release.yaml`.

**Tech Stack:** Python 3.11+, `pyproject.toml` + `src/` layout, `pytest`, `PyYAML`, stdlib `tomllib`/`subprocess`/`argparse`. Matches the hallucination-hunter house style.

## Global Constraints

- Python **3.11+** (uses stdlib `tomllib`).
- `src/` layout; importable package is `delivery_gate`.
- License **MIT**; public OSS under the **ramenprotokol** identity.
- Every check is independently unit-tested for PASS / FAIL / NA paths.
- **Safe default:** anything unknown or unreachable resolves to **FAIL**, never PASS.
- Reports must label each result **AUTO** (machine-proven) or **ATTESTED** (human-claimed) — never overclaim.
- No network required to run the test suite (CI status is injected, not fetched, in v0.1).
- Commit messages end with the trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

```
delivery-gate/
  pyproject.toml
  src/delivery_gate/
    __init__.py
    base.py            # Status, Kind, Result, Check, Context
    manifest.py        # Manifest model + load() + ManifestError
    runner.py          # build_checks(), run_checks(), decide()
    report.py          # render_text(), render_json()
    cli.py             # argparse entrypoint, exit codes
    checks/
      __init__.py
      changelog.py     # ChangelogCheck (AUTO)
      deps_pinned.py   # DepsPinnedCheck (AUTO)
      release_point.py # ReleasePointCheck (AUTO)
      ci_status.py     # CiStatusCheck (AUTO)
      attestation.py   # build_attestation_checks() (ATTESTED)
    adapters/
      __init__.py
      git.py           # GitAdapter (injectable runner)
  tests/
    test_base.py
    test_manifest.py
    test_git_adapter.py
    test_changelog.py
    test_deps_pinned.py
    test_release_point.py
    test_ci_status.py
    test_attestation.py
    test_runner.py
    test_report.py
    test_cli.py
    test_e2e.py
    fixtures/  (created in Task 13)
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/delivery_gate/__init__.py`
- Test: `tests/test_base.py` (placeholder import test)

**Interfaces:**
- Produces: installable package `delivery_gate` with `__version__`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_base.py
def test_package_imports_and_has_version():
    import delivery_gate
    assert delivery_gate.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'delivery_gate'`

- [ ] **Step 3: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "delivery-gate"
version = "0.1.0"
description = "A CLI that gives a hard GO/NO-GO on a release by enforcing a release-readiness checklist."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = ["PyYAML==6.0.2"]

[project.optional-dependencies]
dev = ["pytest==8.3.3"]

[project.scripts]
delivery-gate = "delivery_gate.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: Write the package init**

```python
# src/delivery_gate/__init__.py
"""delivery-gate: a hard GO/NO-GO release gate."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_base.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/delivery_gate/__init__.py tests/test_base.py
git commit -m "feat: scaffold delivery-gate package

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Core types — Status, Kind, Result, Check, Context

**Files:**
- Create: `src/delivery_gate/base.py`
- Test: `tests/test_base.py` (append)

**Interfaces:**
- Produces:
  - `class Status(str, Enum)`: `PASS`, `FAIL`, `NA`
  - `class Kind(str, Enum)`: `AUTO`, `ATTESTED`
  - `@dataclass(frozen=True) Result(check_id: str, label: str, status: Status, kind: Kind, message: str)`
  - `class Check` with attributes `id: str`, `label: str`, `kind: Kind` and method `run(self, context: "Context") -> Result`
  - `@dataclass Context(repo_path: Path, manifest: "Manifest", ci_status: str | None, git: "GitAdapter")`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_base.py (append)
def test_result_and_enums_exist():
    from delivery_gate.base import Status, Kind, Result
    r = Result(check_id="x", label="X", status=Status.PASS, kind=Kind.AUTO, message="ok")
    assert r.status is Status.PASS
    assert r.kind is Kind.AUTO
    assert r.message == "ok"


def test_check_base_requires_run():
    from delivery_gate.base import Check
    import pytest
    with pytest.raises(NotImplementedError):
        Check().run(context=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base.py -v`
Expected: FAIL with `ImportError`/`AttributeError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/base.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from delivery_gate.manifest import Manifest
    from delivery_gate.adapters.git import GitAdapter


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "NA"


class Kind(str, Enum):
    AUTO = "AUTO"          # machine-proven
    ATTESTED = "ATTESTED"  # human-claimed


@dataclass(frozen=True)
class Result:
    check_id: str
    label: str
    status: Status
    kind: Kind
    message: str


@dataclass
class Context:
    repo_path: Path
    manifest: "Manifest"
    ci_status: str | None
    git: "GitAdapter"


class Check:
    id: str = "base"
    label: str = "Base check"
    kind: Kind = Kind.AUTO

    def run(self, context: "Context") -> Result:
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/base.py tests/test_base.py
git commit -m "feat: add core check types (Status, Kind, Result, Check, Context)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Manifest model + loader

**Files:**
- Create: `src/delivery_gate/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass(frozen=True) Attestation(key: str, answer: bool, by: str | None, evidence: str | None)`
  - `@dataclass(frozen=True) Manifest(version: str, attestations: dict[str, Attestation], not_applicable: dict[str, str])`
  - `class ManifestError(Exception)`
  - `load(path: Path) -> Manifest` — raises `ManifestError` with a clear message on missing file / bad YAML / missing `version`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_manifest.py
from pathlib import Path
import pytest
from delivery_gate.manifest import load, Manifest, Attestation, ManifestError


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "release.yaml"
    p.write_text(text)
    return p


def test_loads_valid_manifest(tmp_path):
    p = _write(tmp_path, """
version: "0.1.0"
attestations:
  rollback_tested:
    answer: true
    by: "A. Engineer"
    evidence: "https://example/run"
not_applicable:
  feature_flags: "No flags this release."
""")
    m = load(p)
    assert isinstance(m, Manifest)
    assert m.version == "0.1.0"
    a = m.attestations["rollback_tested"]
    assert a == Attestation("rollback_tested", True, "A. Engineer", "https://example/run")
    assert m.not_applicable["feature_flags"] == "No flags this release."


def test_missing_file_raises_manifest_error(tmp_path):
    with pytest.raises(ManifestError, match="not found"):
        load(tmp_path / "nope.yaml")


def test_missing_version_raises(tmp_path):
    p = _write(tmp_path, "attestations: {}\n")
    with pytest.raises(ManifestError, match="version"):
        load(p)


def test_bad_yaml_raises(tmp_path):
    p = _write(tmp_path, "version: [unterminated\n")
    with pytest.raises(ManifestError):
        load(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/manifest.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class ManifestError(Exception):
    """Raised when release.yaml is missing, malformed, or incomplete."""


@dataclass(frozen=True)
class Attestation:
    key: str
    answer: bool
    by: str | None
    evidence: str | None


@dataclass(frozen=True)
class Manifest:
    version: str
    attestations: dict[str, Attestation]
    not_applicable: dict[str, str]


def load(path: Path) -> Manifest:
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"Release manifest not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"Could not parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path} must be a YAML mapping at the top level.")

    version = raw.get("version")
    if not version:
        raise ManifestError(f"{path} is missing required field 'version'.")

    attestations: dict[str, Attestation] = {}
    for key, val in (raw.get("attestations") or {}).items():
        val = val or {}
        attestations[key] = Attestation(
            key=key,
            answer=bool(val.get("answer", False)),
            by=val.get("by"),
            evidence=val.get("evidence"),
        )

    not_applicable = dict(raw.get("not_applicable") or {})
    return Manifest(
        version=str(version),
        attestations=attestations,
        not_applicable=not_applicable,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_manifest.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/manifest.py tests/test_manifest.py
git commit -m "feat: add release.yaml manifest model and loader

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Git adapter (injectable runner)

**Files:**
- Create: `src/delivery_gate/adapters/__init__.py` (empty)
- Create: `src/delivery_gate/adapters/git.py`
- Test: `tests/test_git_adapter.py`

**Interfaces:**
- Produces `class GitAdapter`:
  - `__init__(self, repo_path: Path, runner: Callable[[list[str]], str] = _default_runner)` where `runner(args)` returns stdout as `str` (args exclude the leading `git`).
  - `is_clean(self) -> bool` — True when `git status --porcelain` is empty.
  - `tag_at_head(self) -> str | None` — the tag pointing at HEAD, or None.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_git_adapter.py
from pathlib import Path
from delivery_gate.adapters.git import GitAdapter


def make_runner(responses):
    calls = []
    def runner(args):
        calls.append(tuple(args))
        key = " ".join(args)
        return responses.get(key, "")
    runner.calls = calls
    return runner


def test_is_clean_true_when_porcelain_empty():
    runner = make_runner({"status --porcelain": ""})
    g = GitAdapter(Path("."), runner=runner)
    assert g.is_clean() is True


def test_is_clean_false_when_changes_present():
    runner = make_runner({"status --porcelain": " M file.py\n"})
    g = GitAdapter(Path("."), runner=runner)
    assert g.is_clean() is False


def test_tag_at_head_returns_tag():
    runner = make_runner({"tag --points-at HEAD": "v0.1.0\n"})
    g = GitAdapter(Path("."), runner=runner)
    assert g.tag_at_head() == "v0.1.0"


def test_tag_at_head_none_when_no_tag():
    runner = make_runner({"tag --points-at HEAD": "\n"})
    g = GitAdapter(Path("."), runner=runner)
    assert g.tag_at_head() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_git_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/adapters/git.py
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable


def _default_runner(repo_path: Path) -> Callable[[list[str]], str]:
    def run(args: list[str]) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout
    return run


class GitAdapter:
    def __init__(self, repo_path: Path, runner: Callable[[list[str]], str] | None = None):
        self.repo_path = Path(repo_path)
        self.runner = runner or _default_runner(self.repo_path)

    def is_clean(self) -> bool:
        return self.runner(["status", "--porcelain"]).strip() == ""

    def tag_at_head(self) -> str | None:
        out = self.runner(["tag", "--points-at", "HEAD"]).strip()
        return out.splitlines()[0] if out else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_git_adapter.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/adapters/ tests/test_git_adapter.py
git commit -m "feat: add git adapter with injectable runner

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: ChangelogCheck (AUTO)

**Files:**
- Create: `src/delivery_gate/checks/__init__.py` (empty)
- Create: `src/delivery_gate/checks/changelog.py`
- Test: `tests/test_changelog.py`

**Interfaces:**
- Consumes: `Context.repo_path`, `Context.manifest.version`.
- Produces: `class ChangelogCheck(Check)` with `id="changelog"`, `kind=Kind.AUTO`; `run` returns PASS if `CHANGELOG.md` contains the version string, FAIL if not present or file missing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_changelog.py
from pathlib import Path
from delivery_gate.base import Status, Kind
from delivery_gate.checks.changelog import ChangelogCheck


def ctx(tmp_path, version):
    from delivery_gate.base import Context
    from delivery_gate.manifest import Manifest
    m = Manifest(version=version, attestations={}, not_applicable={})
    return Context(repo_path=tmp_path, manifest=m, ci_status=None, git=None)


def test_pass_when_version_present(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0 - 2026-06-24\n- first\n")
    r = ChangelogCheck().run(ctx(tmp_path, "0.1.0"))
    assert r.status is Status.PASS
    assert r.kind is Kind.AUTO


def test_fail_when_version_absent(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.0.9\n")
    r = ChangelogCheck().run(ctx(tmp_path, "0.1.0"))
    assert r.status is Status.FAIL


def test_fail_when_file_missing(tmp_path):
    r = ChangelogCheck().run(ctx(tmp_path, "0.1.0"))
    assert r.status is Status.FAIL
    assert "CHANGELOG.md" in r.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_changelog.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/checks/changelog.py
from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status


class ChangelogCheck(Check):
    id = "changelog"
    label = "CHANGELOG updated for this version"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        path = context.repo_path / "CHANGELOG.md"
        version = context.manifest.version
        if not path.exists():
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "CHANGELOG.md not found at repo root.")
        text = path.read_text()
        if version in text:
            return Result(self.id, self.label, Status.PASS, self.kind,
                          f"Found an entry for {version}.")
        return Result(self.id, self.label, Status.FAIL, self.kind,
                      f"No CHANGELOG.md entry mentions {version}.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_changelog.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/checks/ tests/test_changelog.py
git commit -m "feat: add changelog auto-check

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: DepsPinnedCheck (AUTO)

**Files:**
- Create: `src/delivery_gate/checks/deps_pinned.py`
- Test: `tests/test_deps_pinned.py`

**Interfaces:**
- Consumes: `Context.repo_path`.
- Produces: `class DepsPinnedCheck(Check)` with `id="deps_pinned"`, `kind=Kind.AUTO`. Reads `pyproject.toml` `[project].dependencies` (via `tomllib`). PASS if every dependency uses an exact pin `==`; FAIL listing unpinned ones; PASS with an explanatory message if no dependencies are declared.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deps_pinned.py
from delivery_gate.base import Status
from delivery_gate.checks.deps_pinned import DepsPinnedCheck


def ctx(tmp_path):
    from delivery_gate.base import Context
    from delivery_gate.manifest import Manifest
    m = Manifest(version="0.1.0", attestations={}, not_applicable={})
    return Context(repo_path=tmp_path, manifest=m, ci_status=None, git=None)


def test_pass_when_all_pinned(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.1.0"\ndependencies=["PyYAML==6.0.2","rich==13.9.0"]\n'
    )
    assert DepsPinnedCheck().run(ctx(tmp_path)).status is Status.PASS


def test_fail_when_unpinned(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.1.0"\ndependencies=["PyYAML>=6","rich==13.9.0"]\n'
    )
    r = DepsPinnedCheck().run(ctx(tmp_path))
    assert r.status is Status.FAIL
    assert "PyYAML" in r.message


def test_pass_when_no_deps(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0.1.0"\n')
    r = DepsPinnedCheck().run(ctx(tmp_path))
    assert r.status is Status.PASS


def test_fail_when_no_pyproject(tmp_path):
    r = DepsPinnedCheck().run(ctx(tmp_path))
    assert r.status is Status.FAIL
    assert "pyproject.toml" in r.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deps_pinned.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/checks/deps_pinned.py
from __future__ import annotations

import tomllib

from delivery_gate.base import Check, Context, Kind, Result, Status


class DepsPinnedCheck(Check):
    id = "deps_pinned"
    label = "Dependencies pinned to exact versions"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        path = context.repo_path / "pyproject.toml"
        if not path.exists():
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "pyproject.toml not found; cannot verify pinned dependencies.")
        data = tomllib.loads(path.read_text())
        deps = (data.get("project") or {}).get("dependencies") or []
        if not deps:
            return Result(self.id, self.label, Status.PASS, self.kind,
                          "No declared dependencies to pin.")
        unpinned = [d for d in deps if "==" not in d]
        if unpinned:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "Unpinned dependencies: " + ", ".join(unpinned))
        return Result(self.id, self.label, Status.PASS, self.kind,
                      f"All {len(deps)} dependencies are pinned.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deps_pinned.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/checks/deps_pinned.py tests/test_deps_pinned.py
git commit -m "feat: add dependencies-pinned auto-check

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: ReleasePointCheck (AUTO)

**Files:**
- Create: `src/delivery_gate/checks/release_point.py`
- Test: `tests/test_release_point.py`

**Interfaces:**
- Consumes: `Context.git` (`is_clean()`, `tag_at_head()`), `Context.manifest.version`.
- Produces: `class ReleasePointCheck(Check)` with `id="release_point"`, `kind=Kind.AUTO`. PASS only if the tree is clean AND a tag at HEAD matches the version (tag `v0.1.0` or `0.1.0` both match version `0.1.0`). FAIL otherwise, listing each failing reason.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_release_point.py
from delivery_gate.base import Status
from delivery_gate.checks.release_point import ReleasePointCheck


class FakeGit:
    def __init__(self, clean, tag):
        self._clean, self._tag = clean, tag
    def is_clean(self):
        return self._clean
    def tag_at_head(self):
        return self._tag


def ctx(version, git):
    from delivery_gate.base import Context
    from delivery_gate.manifest import Manifest
    m = Manifest(version=version, attestations={}, not_applicable={})
    return Context(repo_path=None, manifest=m, ci_status=None, git=git)


def test_pass_clean_and_tag_matches_with_v():
    r = ReleasePointCheck().run(ctx("0.1.0", FakeGit(True, "v0.1.0")))
    assert r.status is Status.PASS


def test_pass_clean_and_tag_matches_without_v():
    r = ReleasePointCheck().run(ctx("0.1.0", FakeGit(True, "0.1.0")))
    assert r.status is Status.PASS


def test_fail_dirty_tree():
    r = ReleasePointCheck().run(ctx("0.1.0", FakeGit(False, "v0.1.0")))
    assert r.status is Status.FAIL
    assert "uncommitted" in r.message.lower()


def test_fail_tag_mismatch():
    r = ReleasePointCheck().run(ctx("0.1.0", FakeGit(True, "v0.2.0")))
    assert r.status is Status.FAIL
    assert "tag" in r.message.lower()


def test_fail_no_tag():
    r = ReleasePointCheck().run(ctx("0.1.0", FakeGit(True, None)))
    assert r.status is Status.FAIL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_release_point.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/checks/release_point.py
from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status


class ReleasePointCheck(Check):
    id = "release_point"
    label = "Clean, tagged release point"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        version = context.manifest.version
        git = context.git
        reasons: list[str] = []

        if not git.is_clean():
            reasons.append("working tree has uncommitted changes")

        tag = git.tag_at_head()
        if tag is None:
            reasons.append("no git tag points at HEAD")
        elif tag.lstrip("v") != version.lstrip("v"):
            reasons.append(f"tag '{tag}' does not match manifest version '{version}'")

        if reasons:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "; ".join(reasons))
        return Result(self.id, self.label, Status.PASS, self.kind,
                      f"Clean tree on tag '{tag}' matching {version}.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_release_point.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/checks/release_point.py tests/test_release_point.py
git commit -m "feat: add clean-release-point auto-check

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: CiStatusCheck (AUTO)

**Files:**
- Create: `src/delivery_gate/checks/ci_status.py`
- Test: `tests/test_ci_status.py`

**Interfaces:**
- Consumes: `Context.ci_status` (a string like `"success"`/`"failure"`, or `None`).
- Produces: `class CiStatusCheck(Check)` with `id="ci_status"`, `kind=Kind.AUTO`. PASS only when `ci_status == "success"` (case-insensitive). `None`/unknown/anything else → FAIL (safe default).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ci_status.py
from delivery_gate.base import Status
from delivery_gate.checks.ci_status import CiStatusCheck


def ctx(ci_status):
    from delivery_gate.base import Context
    from delivery_gate.manifest import Manifest
    m = Manifest(version="0.1.0", attestations={}, not_applicable={})
    return Context(repo_path=None, manifest=m, ci_status=ci_status, git=None)


def test_pass_on_success():
    assert CiStatusCheck().run(ctx("success")).status is Status.PASS


def test_pass_case_insensitive():
    assert CiStatusCheck().run(ctx("SUCCESS")).status is Status.PASS


def test_fail_on_failure():
    assert CiStatusCheck().run(ctx("failure")).status is Status.FAIL


def test_fail_on_unknown_none():
    r = CiStatusCheck().run(ctx(None))
    assert r.status is Status.FAIL
    assert "unknown" in r.message.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ci_status.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/checks/ci_status.py
from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status


class CiStatusCheck(Check):
    id = "ci_status"
    label = "Tests passed in CI"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        status = (context.ci_status or "").strip().lower()
        if status == "success":
            return Result(self.id, self.label, Status.PASS, self.kind,
                          "CI reported success.")
        if not status:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "CI status unknown (none provided) — treating as a fail.")
        return Result(self.id, self.label, Status.FAIL, self.kind,
                      f"CI status is '{status}', not 'success'.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ci_status.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/checks/ci_status.py tests/test_ci_status.py
git commit -m "feat: add CI-status auto-check (fail-safe default)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Attestation checks (ATTESTED)

**Files:**
- Create: `src/delivery_gate/checks/attestation.py`
- Test: `tests/test_attestation.py`

**Interfaces:**
- Consumes: `Context.manifest.attestations`, `Context.manifest.not_applicable`.
- Produces:
  - `REQUIRED_ATTESTATIONS: list[tuple[str, str]]` — pairs of `(key, label)` covering the human-judgment checklist items: `rollback_tested`, `oncall_notified`, `approver_signed_off`, `monitoring_reviewed`.
  - `build_attestation_checks() -> list[Check]` — one `Check` per required attestation.
  - Each check: NA if its key is in `not_applicable` (message includes the reason); PASS if the attestation exists, `answer is True`, and `by` is set; FAIL otherwise (missing, `false`, or no attester).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_attestation.py
from delivery_gate.base import Status, Kind
from delivery_gate.manifest import Manifest, Attestation
from delivery_gate.checks.attestation import build_attestation_checks, REQUIRED_ATTESTATIONS


def ctx(attestations, not_applicable=None):
    from delivery_gate.base import Context
    m = Manifest(version="0.1.0", attestations=attestations, not_applicable=not_applicable or {})
    return Context(repo_path=None, manifest=m, ci_status=None, git=None)


def run_all(context):
    return {c.id: c.run(context) for c in build_attestation_checks()}


def test_one_check_per_required_item():
    assert len(build_attestation_checks()) == len(REQUIRED_ATTESTATIONS)


def test_pass_when_attested_true_with_by():
    att = {"rollback_tested": Attestation("rollback_tested", True, "Eng", None)}
    res = run_all(ctx(att))["rollback_tested"]
    assert res.status is Status.PASS
    assert res.kind is Kind.ATTESTED


def test_fail_when_answer_false():
    att = {"rollback_tested": Attestation("rollback_tested", False, "Eng", None)}
    assert run_all(ctx(att))["rollback_tested"].status is Status.FAIL


def test_fail_when_missing():
    assert run_all(ctx({}))["rollback_tested"].status is Status.FAIL


def test_fail_when_no_attester():
    att = {"rollback_tested": Attestation("rollback_tested", True, None, None)}
    assert run_all(ctx(att))["rollback_tested"].status is Status.FAIL


def test_na_when_listed_not_applicable():
    res = run_all(ctx({}, not_applicable={"rollback_tested": "No prod deploy."}))["rollback_tested"]
    assert res.status is Status.NA
    assert "No prod deploy." in res.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_attestation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/checks/attestation.py
from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status

REQUIRED_ATTESTATIONS: list[tuple[str, str]] = [
    ("rollback_tested", "Rollback procedure tested"),
    ("oncall_notified", "On-call engineer notified"),
    ("approver_signed_off", "Named approver signed off"),
    ("monitoring_reviewed", "Monitoring and alerts reviewed"),
]


class AttestationCheck(Check):
    kind = Kind.ATTESTED

    def __init__(self, key: str, label: str):
        self.id = key
        self.label = label

    def run(self, context: Context) -> Result:
        na = context.manifest.not_applicable.get(self.id)
        if na is not None:
            return Result(self.id, self.label, Status.NA, self.kind,
                          f"Marked not applicable: {na}")
        att = context.manifest.attestations.get(self.id)
        if att is None:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "No attestation provided in release.yaml.")
        if not att.answer:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "Attested as not done (answer: false).")
        if not att.by:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "Attestation has no attester ('by' is empty).")
        evidence = f" Evidence: {att.evidence}" if att.evidence else ""
        return Result(self.id, self.label, Status.PASS, self.kind,
                      f"Attested by {att.by}.{evidence}")


def build_attestation_checks() -> list[Check]:
    return [AttestationCheck(key, label) for key, label in REQUIRED_ATTESTATIONS]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_attestation.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/checks/attestation.py tests/test_attestation.py
git commit -m "feat: add manifest-backed attestation checks

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 10: Runner (build, run, decide)

**Files:**
- Create: `src/delivery_gate/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: all checks + `Context`.
- Produces:
  - `build_checks() -> list[Check]` — the four auto-checks plus `build_attestation_checks()`.
  - `run_checks(context: Context) -> list[Result]` — runs every check in order.
  - `decide(results: list[Result]) -> bool` — returns True (GO) iff no `Result.status is Status.FAIL` (NA does not block).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_runner.py
from delivery_gate.base import Result, Status, Kind
from delivery_gate.runner import build_checks, decide


def test_build_checks_has_four_auto_plus_attestations():
    checks = build_checks()
    auto = [c for c in checks if c.kind is Kind.AUTO]
    attested = [c for c in checks if c.kind is Kind.ATTESTED]
    assert len(auto) == 4
    assert len(attested) == 4


def _r(status):
    return Result("x", "X", status, Kind.AUTO, "")


def test_decide_go_when_no_fail():
    assert decide([_r(Status.PASS), _r(Status.NA)]) is True


def test_decide_nogo_when_any_fail():
    assert decide([_r(Status.PASS), _r(Status.FAIL)]) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/runner.py
from __future__ import annotations

from delivery_gate.base import Check, Context, Result, Status
from delivery_gate.checks.attestation import build_attestation_checks
from delivery_gate.checks.changelog import ChangelogCheck
from delivery_gate.checks.ci_status import CiStatusCheck
from delivery_gate.checks.deps_pinned import DepsPinnedCheck
from delivery_gate.checks.release_point import ReleasePointCheck


def build_checks() -> list[Check]:
    auto: list[Check] = [
        ChangelogCheck(),
        CiStatusCheck(),
        DepsPinnedCheck(),
        ReleasePointCheck(),
    ]
    return auto + build_attestation_checks()


def run_checks(context: Context) -> list[Result]:
    return [check.run(context) for check in build_checks()]


def decide(results: list[Result]) -> bool:
    return not any(r.status is Status.FAIL for r in results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_runner.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/runner.py tests/test_runner.py
git commit -m "feat: add runner that builds, runs, and decides GO/NO-GO

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 11: Reporter (text + JSON)

**Files:**
- Create: `src/delivery_gate/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `list[Result]`, `go: bool`.
- Produces:
  - `render_text(results: list[Result], go: bool) -> str` — one line per result tagged `[AUTO]`/`[ATTESTED]` with PASS/FAIL/NA; a hold-reasons block listing every FAIL when NO-GO; a final `GO` / `NO-GO` line.
  - `render_json(results: list[Result], go: bool) -> str` — JSON with `decision` (`"GO"`/`"NO-GO"`) and a `results` array of `{check_id,label,status,kind,message}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report.py
import json
from delivery_gate.base import Result, Status, Kind
from delivery_gate.report import render_text, render_json

RESULTS = [
    Result("changelog", "CHANGELOG updated", Status.PASS, Kind.AUTO, "ok"),
    Result("rollback_tested", "Rollback tested", Status.FAIL, Kind.ATTESTED, "missing"),
    Result("oncall_notified", "On-call notified", Status.NA, Kind.ATTESTED, "n/a"),
]


def test_text_lists_results_and_decision():
    out = render_text(RESULTS, go=False)
    assert "[AUTO]" in out and "[ATTESTED]" in out
    assert "NO-GO" in out
    assert "Rollback tested" in out  # hold reason listed


def test_text_go_line_when_go():
    out = render_text([RESULTS[0]], go=True)
    assert "GO" in out and "NO-GO" not in out


def test_json_shape():
    out = render_json(RESULTS, go=False)
    data = json.loads(out)
    assert data["decision"] == "NO-GO"
    assert len(data["results"]) == 3
    assert data["results"][0]["check_id"] == "changelog"
    assert data["results"][0]["status"] == "PASS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/report.py
from __future__ import annotations

import json

from delivery_gate.base import Result, Status

_SYMBOL = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.NA: "NA  "}


def render_text(results: list[Result], go: bool) -> str:
    lines = ["delivery-gate report", "=" * 40]
    for r in results:
        lines.append(f"[{r.kind.value:<8}] {_SYMBOL[r.status]}  {r.label} — {r.message}")
    fails = [r for r in results if r.status is Status.FAIL]
    if not go and fails:
        lines.append("")
        lines.append("Hold reasons (NO-GO):")
        for r in fails:
            lines.append(f"  - {r.label}: {r.message}")
    lines.append("")
    lines.append("Decision: " + ("GO" if go else "NO-GO"))
    return "\n".join(lines)


def render_json(results: list[Result], go: bool) -> str:
    payload = {
        "decision": "GO" if go else "NO-GO",
        "results": [
            {
                "check_id": r.check_id,
                "label": r.label,
                "status": r.status.value,
                "kind": r.kind.value,
                "message": r.message,
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/report.py tests/test_report.py
git commit -m "feat: add text and JSON reporters

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 12: CLI (argparse + exit codes)

**Files:**
- Create: `src/delivery_gate/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `manifest.load`, `runner.run_checks`/`decide`, `report.render_text`/`render_json`, `GitAdapter`.
- Produces:
  - `main(argv: list[str] | None = None) -> int` — subcommand `check` with flags `--repo PATH` (default `.`), `--ci-status STATUS` (default from env `DELIVERY_GATE_CI_STATUS`), `--json`. Loads `<repo>/release.yaml`. Returns `0` on GO, `1` on NO-GO, `2` on usage/manifest error (prints the error to stderr).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
from pathlib import Path
from delivery_gate.cli import main


def _passing_repo(tmp_path: Path):
    (tmp_path / "CHANGELOG.md").write_text("## 0.1.0\n- ok\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0.1.0"\ndependencies=["PyYAML==6.0.2"]\n')
    (tmp_path / "release.yaml").write_text(
        "version: \"0.1.0\"\n"
        "attestations:\n"
        "  rollback_tested: {answer: true, by: Eng}\n"
        "  oncall_notified: {answer: true, by: Eng}\n"
        "  approver_signed_off: {answer: true, by: Boss}\n"
        "  monitoring_reviewed: {answer: true, by: Eng}\n"
    )
    return tmp_path


def test_go_returns_zero(tmp_path, monkeypatch):
    repo = _passing_repo(tmp_path)
    # Force git checks green by stubbing GitAdapter via env-independent monkeypatch:
    import delivery_gate.cli as climod
    class FakeGit:
        def __init__(self, *a, **k): pass
        def is_clean(self): return True
        def tag_at_head(self): return "v0.1.0"
    monkeypatch.setattr(climod, "GitAdapter", FakeGit)
    rc = main(["check", "--repo", str(repo), "--ci-status", "success"])
    assert rc == 0


def test_nogo_returns_one(tmp_path, monkeypatch):
    repo = _passing_repo(tmp_path)
    import delivery_gate.cli as climod
    class FakeGit:
        def __init__(self, *a, **k): pass
        def is_clean(self): return True
        def tag_at_head(self): return "v0.1.0"
    monkeypatch.setattr(climod, "GitAdapter", FakeGit)
    rc = main(["check", "--repo", str(repo), "--ci-status", "failure"])
    assert rc == 1


def test_missing_manifest_returns_two(tmp_path, capsys):
    rc = main(["check", "--repo", str(tmp_path), "--ci-status", "success"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/delivery_gate/cli.py
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from delivery_gate.adapters.git import GitAdapter
from delivery_gate.base import Context
from delivery_gate.manifest import ManifestError, load
from delivery_gate.report import render_json, render_text
from delivery_gate.runner import decide, run_checks


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="delivery-gate")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Run the release gate.")
    check.add_argument("--repo", default=".", help="Path to the repo (default: .)")
    check.add_argument("--ci-status", default=os.environ.get("DELIVERY_GATE_CI_STATUS"),
                       help="CI outcome for the gated commit, e.g. 'success'.")
    check.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo = Path(args.repo)
    try:
        manifest = load(repo / "release.yaml")
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    context = Context(
        repo_path=repo,
        manifest=manifest,
        ci_status=args.ci_status,
        git=GitAdapter(repo),
    )
    results = run_checks(context)
    go = decide(results)
    output = render_json(results, go) if args.json else render_text(results, go)
    print(output)
    return 0 if go else 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/delivery_gate/cli.py tests/test_cli.py
git commit -m "feat: add CLI entrypoint with GO/NO-GO exit codes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 13: End-to-end fixtures + README

**Files:**
- Create: `tests/fixtures/pass_repo/` (CHANGELOG.md, pyproject.toml, release.yaml)
- Create: `tests/fixtures/fail_repo/` (CHANGELOG.md missing the version, a `false` attestation)
- Create: `tests/test_e2e.py`
- Create: `README.md`, `CHANGELOG.md`, `LICENSE`

**Interfaces:**
- Consumes: `delivery_gate.cli.main` with a stubbed `GitAdapter` (so e2e needs no real git).

- [ ] **Step 1: Write the failing e2e test**

```python
# tests/test_e2e.py
from pathlib import Path
import delivery_gate.cli as climod

FIX = Path(__file__).parent / "fixtures"


class FakeGit:
    def __init__(self, *a, **k): pass
    def is_clean(self): return True
    def tag_at_head(self): return "v0.1.0"


def test_pass_repo_is_go(monkeypatch):
    monkeypatch.setattr(climod, "GitAdapter", FakeGit)
    rc = climod.main(["check", "--repo", str(FIX / "pass_repo"), "--ci-status", "success"])
    assert rc == 0


def test_fail_repo_is_nogo(monkeypatch, capsys):
    monkeypatch.setattr(climod, "GitAdapter", FakeGit)
    rc = climod.main(["check", "--repo", str(FIX / "fail_repo"), "--ci-status", "success"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "NO-GO" in out
```

- [ ] **Step 2: Create the pass_repo fixture**

```
tests/fixtures/pass_repo/CHANGELOG.md:
## 0.1.0 - 2026-06-24
- initial release

tests/fixtures/pass_repo/pyproject.toml:
[project]
name = "demo"
version = "0.1.0"
dependencies = ["PyYAML==6.0.2"]

tests/fixtures/pass_repo/release.yaml:
version: "0.1.0"
attestations:
  rollback_tested: {answer: true, by: Eng, evidence: "https://example/run"}
  oncall_notified: {answer: true, by: Eng}
  approver_signed_off: {answer: true, by: Boss}
  monitoring_reviewed: {answer: true, by: Eng}
```

- [ ] **Step 3: Create the fail_repo fixture**

```
tests/fixtures/fail_repo/CHANGELOG.md:
## 0.0.9 - 2026-01-01
- old entry (no 0.1.0 entry on purpose)

tests/fixtures/fail_repo/pyproject.toml:
[project]
name = "demo"
version = "0.1.0"
dependencies = ["PyYAML==6.0.2"]

tests/fixtures/fail_repo/release.yaml:
version: "0.1.0"
attestations:
  rollback_tested: {answer: false, by: Eng}
  oncall_notified: {answer: true, by: Eng}
  approver_signed_off: {answer: true, by: Boss}
  monitoring_reviewed: {answer: true, by: Eng}
```

- [ ] **Step 4: Run e2e tests to verify they pass**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Write README.md, CHANGELOG.md, LICENSE**

`README.md` — what it is (plain), install (`pipx install delivery-gate` once published), a `release.yaml` example, the `delivery-gate check --ci-status success` command, the four auto-checks vs attestation split, and the AUTO/ATTESTED honesty note.
`CHANGELOG.md` — a `## 0.1.0` entry describing the first release (this also makes delivery-gate pass its **own** gate — a nice proof).
`LICENSE` — MIT, ramenprotokol.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures tests/test_e2e.py README.md CHANGELOG.md LICENSE
git commit -m "test: add end-to-end pass/fail fixtures + project docs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] `python -m pytest -v` — entire suite green.
- [ ] `pip install -e .` then `delivery-gate check --repo . --ci-status success` runs and prints a report (delivery-gate gating itself).
- [ ] Opus review pass (xhigh): read the full diff, re-run tests, check honesty labeling and fail-safe defaults.
- [ ] Run `/privacyramen` before any push. Run the Repo Audit Crew before going public (PROJECT_CONVENTIONS Rule 2).

## Spec coverage check

- Auto-checks (changelog, CI, deps, release point) → Tasks 5–8. ✓
- Attestation manifest + checks → Tasks 3, 9. ✓
- CI-gate exit codes → Task 12. ✓
- Pluggable-check architecture (base interface, runner, reporter) → Tasks 2, 10, 11. ✓
- Error handling (bad manifest → exit 2; CI unknown → FAIL) → Tasks 3, 8, 12. ✓
- Honesty labeling (AUTO vs ATTESTED) → Tasks 2, 11. ✓
- Testing standard (unit per check + e2e) → Tasks 4–13. ✓
