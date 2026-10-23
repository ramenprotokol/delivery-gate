from __future__ import annotations

import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from delivery_gate.adapters.git import GitAdapter
from delivery_gate.base import Context
from delivery_gate.investigate import DEFAULT_MAX_STEPS, Brief, investigate
from delivery_gate.llm import ChatReply, LlmError
from delivery_gate.manifest import load
from delivery_gate.tools import Toolbox, ToolError

# Test cases run the real `investigate` flow, unchanged, against made-up repos
# and write a plain-text run log. Nothing here alters the system prompt, the
# tools or the decision logic: the client is wrapped to record what it sends and
# receives, and Toolbox.dispatch is wrapped to record each tool result.

# The tool names a case may use in must_call / must_not_call. `finish` is the
# model's way of ending; the rest come from the Toolbox.
TOOL_NAMES = (
    "git_status",
    "git_tags",
    "list_files",
    "read_file",
    "read_manifest",
    "ci_status",
    "run_checks",
    "finish",
)

_EXPECT_KEYS = {
    "decision",
    "findings_mention",
    "findings_not_mention",
    "must_call",
    "must_not_call",
    "max_findings",
}

_MODEL_TEXT_LIMIT = 500
_TOOL_RESULT_LIMIT = 300
_SUMMARY_LIMIT = 300
_FINDING_LIMIT = 300

_COMMIT_DATE = "2020-01-01T00:00:00+0000"


class CasesError(ValueError):
    """Raised for a bad cases or repos file (a usage error, not a case failure)."""


@dataclass(frozen=True)
class Case:
    id: object
    purpose: str
    command: str
    repo: str
    ci_status: str | None
    expect: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CaseResult:
    case: Case
    passed: bool
    reasons: list[str]


# ---------------------------------------------------------------- file loading


def load_repos(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CasesError(f"cannot read repos file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CasesError("repos file must be a JSON object of repo name -> spec.")
    for name, spec in data.items():
        if not isinstance(spec, dict):
            raise CasesError(f"repo {name!r}: spec must be an object.")
        for key in spec:
            if key not in {"files", "tags", "uncommitted", "untracked"}:
                raise CasesError(f"repo {name!r}: unknown key {key!r}.")
        for key in ("files", "uncommitted", "untracked"):
            block = spec.get(key, {})
            if not isinstance(block, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in block.items()
            ):
                raise CasesError(f"repo {name!r}: {key!r} must map file paths to text.")
            for rel in block:
                _check_relative(name, rel)
        tags = spec.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) and t for t in tags):
            raise CasesError(f"repo {name!r}: 'tags' must be a list of tag names.")
    return data


def _check_relative(repo: str, rel: str) -> None:
    candidate = Path(rel)
    if not rel or candidate.is_absolute() or ".." in candidate.parts:
        raise CasesError(f"repo {repo!r}: file path {rel!r} must be relative and stay inside.")


def load_cases(path: Path, repos: dict[str, dict]) -> list[Case]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CasesError(f"cannot read cases file {path}: {exc}") from exc
    cases: list[Case] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError as exc:
            raise CasesError(f"cases line {number}: not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise CasesError(f"cases line {number}: must be a JSON object.")
        repo = raw.get("repo")
        if not isinstance(repo, str) or repo not in repos:
            raise CasesError(f"cases line {number}: unknown repo {repo!r}.")
        if "id" not in raw:
            raise CasesError(f"cases line {number}: missing 'id'.")
        expect = raw.get("expect") or {}
        _check_expect(number, expect)
        ci_status = raw.get("ci_status")
        if ci_status is not None and not isinstance(ci_status, str):
            raise CasesError(f"cases line {number}: 'ci_status' must be text.")
        cases.append(
            Case(
                id=raw["id"],
                purpose=str(raw.get("purpose", "")),
                command=str(raw.get("command", "")),
                repo=repo,
                ci_status=ci_status,
                expect=expect,
            )
        )
    return cases


def _check_expect(number: int, expect: object) -> None:
    where = f"cases line {number}"
    if not isinstance(expect, dict):
        raise CasesError(f"{where}: 'expect' must be an object.")
    unknown = set(expect) - _EXPECT_KEYS
    if unknown:
        raise CasesError(f"{where}: unknown expect keys {sorted(unknown)}.")
    decision = expect.get("decision")
    if decision is not None and decision not in ("GO", "NO-GO"):
        raise CasesError(f"{where}: expect.decision must be GO or NO-GO.")
    for key in ("findings_mention", "findings_not_mention", "must_call", "must_not_call"):
        value = expect.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise CasesError(f"{where}: expect.{key} must be a list of text.")
    for key in ("must_call", "must_not_call"):
        for name in expect.get(key, []):
            if name not in TOOL_NAMES:
                raise CasesError(f"{where}: expect.{key} has unknown tool {name!r}.")
    limit = expect.get("max_findings")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        raise CasesError(f"{where}: expect.max_findings must be a whole number or null.")


# ---------------------------------------------------------------- repo builder


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Mock",
        "GIT_AUTHOR_EMAIL": "mock@example.invalid",
        "GIT_COMMITTER_NAME": "Mock",
        "GIT_COMMITTER_EMAIL": "mock@example.invalid",
        "GIT_AUTHOR_DATE": _COMMIT_DATE,
        "GIT_COMMITTER_DATE": _COMMIT_DATE,
    }
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr.strip().splitlines() or [f"exit code {proc.returncode}"])[-1]
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def build_repo(spec: dict, root: Path) -> None:
    """Build a made-up repo in `root`: commit files, tag HEAD, then dirty it."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    files = spec.get("files") or {}
    _write(root, files)
    if files:
        _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", "Initial commit")
    for tag in spec.get("tags") or []:
        _git(root, "tag", tag)
    _write(root, spec.get("uncommitted") or {})
    _write(root, spec.get("untracked") or {})


# -------------------------------------------------------------------- recorder


class RunLog:
    """Collects log text and scrubs the API key from everything it writes."""

    def __init__(self, secrets: list[str]):
        self.lines: list[str] = []
        self._secrets = [s for s in secrets if s]
        self._paths: list[str] = []

    def mask_path(self, *paths: Path) -> None:
        """Show these (temp) paths as <repo> so logs do not depend on where they were."""
        self._paths.extend(str(p) for p in paths)

    def scrub(self, text: str) -> str:
        for path in self._paths:
            text = text.replace(path, "<repo>")
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    def add(self, text: str = "") -> None:
        self.lines.append(self.scrub(text))

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _clip(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class RecordingClient:
    """Wraps a chat client: forwards every call unchanged and records it."""

    def __init__(self, inner, log: RunLog):
        self._inner = inner
        self._log = log
        self.model = getattr(inner, "model", "")
        self.system_prompt: str | None = None
        self.tools: list[dict] | None = None
        self.errors: list[str] = []
        self.calls: list[str] = []

    def chat(self, messages, tools=None, model=None) -> ChatReply:
        if self.system_prompt is None and messages and messages[0].get("role") == "system":
            self.system_prompt = str(messages[0].get("content", ""))
        if tools and self.tools is None:
            self.tools = tools
        try:
            reply = self._inner.chat(messages, tools=tools, model=model)
        except LlmError as exc:
            self.errors.append(str(exc))
            self._log.add(f"  model API error: {_clip(str(exc), _MODEL_TEXT_LIMIT)}")
            raise
        if reply.content.strip():
            self._log.add(f'  model: "{_clip(reply.content, _MODEL_TEXT_LIMIT)}"')
        for call in reply.tool_calls:
            if call.name == "finish":
                self.calls.append("finish")
                self._log.add(f"  tool call: finish({_clip(call.arguments, _TOOL_RESULT_LIMIT)})")
        return reply


@contextmanager
def _record_tools(client: RecordingClient, log: RunLog):
    """Log every Toolbox.dispatch (name, arguments, result) without changing it."""
    original = Toolbox.dispatch

    def recording(self, name, arguments):
        client.calls.append(name)
        try:
            output = original(self, name, arguments)
        except ToolError as exc:
            output = json.dumps({"error": str(exc)})
            log.add(
                f"  tool call: {name}({_clip(arguments, _TOOL_RESULT_LIMIT)}) "
                f"-> {_clip(output, _TOOL_RESULT_LIMIT)}"
            )
            raise
        log.add(
            f"  tool call: {name}({_clip(arguments, _TOOL_RESULT_LIMIT)}) "
            f"-> {_clip(output, _TOOL_RESULT_LIMIT)}"
        )
        return output

    Toolbox.dispatch = recording
    try:
        yield
    finally:
        Toolbox.dispatch = original


# ---------------------------------------------------------------------- judging


def _findings_text(brief: Brief) -> str:
    parts = [brief.summary]
    for item in [*brief.blocking, *brief.notes]:
        parts.extend([item.check_id, item.label, item.explanation, item.fix or ""])
    return "\n".join(parts).lower()


def _judge(case: Case, brief: Brief, calls: list[str], errors: list[str]) -> list[str]:
    reasons: list[str] = []
    if errors:
        reasons.append(f"model API error: {_clip(errors[0], 200)}")
    expect = case.expect
    decision = expect.get("decision")
    if decision and brief.decision != decision:
        reasons.append(f"decision was {brief.decision}, expected {decision}")
    text = _findings_text(brief)
    for needle in expect.get("findings_mention", []):
        if needle.lower() not in text:
            reasons.append(f'findings never mention "{needle}"')
    for needle in expect.get("findings_not_mention", []):
        if needle.lower() in text:
            reasons.append(f'findings mention "{needle}" but should not')
    for name in expect.get("must_call", []):
        if name not in calls:
            reasons.append(f"never called {name}")
    for name in expect.get("must_not_call", []):
        if name in calls:
            reasons.append(f"called {name} but should not have")
    limit = expect.get("max_findings")
    count = len(brief.blocking) + len(brief.notes)
    if limit is not None and count > limit:
        reasons.append(f"{count} findings, expected at most {limit}")
    return reasons


def _brief_line(brief: Brief) -> list[str]:
    items = [*brief.blocking, *brief.notes]
    lines = [
        f"  brief: {brief.decision} | {_clip(brief.summary, _SUMMARY_LIMIT)} "
        f"| findings: {len(items)}"
    ]
    for item in items:
        fix = f" fix: {item.fix}" if item.fix else ""
        lines.append(f"    - [{item.check_id}] {_clip(item.explanation + fix, _FINDING_LIMIT)}")
    return lines


# ----------------------------------------------------------------------- runner


def _endpoint(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc.rpartition('@')[2]}" if parsed.netloc else ""


def _run_one(
    case: Case, spec: dict, client, log: RunLog, max_steps: int, shown: dict
) -> CaseResult:
    log.add(f"case {case.id}  ({case.purpose})")
    log.add(f"  user: {case.command}   [repo {case.repo}]")
    with tempfile.TemporaryDirectory(prefix="delivery-gate-case-") as tmp:
        root = Path(tmp) / "repo"
        log.mask_path(root, root.resolve())
        recorder = RecordingClient(client, log)
        brief = None
        try:
            build_repo(spec, root)
            context = Context(
                repo_path=root,
                manifest=load(root / "release.yaml"),
                ci_status=case.ci_status,
                git=GitAdapter(root),
            )
            with _record_tools(recorder, log):
                brief = investigate(context, recorder, max_steps=max_steps)
        except Exception as exc:  # one broken case must not stop the run
            reasons = [f"crashed: {type(exc).__name__}: {_clip(str(exc), 200)}"]
        else:
            reasons = _judge(case, brief, recorder.calls, recorder.errors)
        reasons = [log.scrub(r) for r in reasons]
        _stage_setup(log, recorder, shown, root)
    if brief is not None:
        for line in _brief_line(brief):
            log.add(line)
    return _finish_case(case, log, reasons)


def _finish_case(case: Case, log: RunLog, reasons: list[str]) -> CaseResult:
    if reasons:
        log.add(f"  result: FAIL  ({'; '.join(reasons)})")
    else:
        log.add("  result: PASS")
    log.add()
    return CaseResult(case=case, passed=not reasons, reasons=reasons)


def _stage_setup(log: RunLog, recorder: RecordingClient, shown: dict, root: Path) -> None:
    """Note the system prompt and tools sent, only when they differ from the last case."""
    if recorder.system_prompt is not None:
        prompt = recorder.system_prompt
        for path in (str(root), str(root.resolve())):
            prompt = prompt.replace(path, "<repo>")
        if prompt != shown.get("prompt"):
            shown["prompt"] = prompt
            shown["staged"].append(f"system prompt:\n{prompt}")
    if recorder.tools is not None:
        rendered = json.dumps(recorder.tools, indent=2)
        if rendered != shown.get("tools"):
            shown["tools"] = rendered
            shown["staged"].append(f"tools:\n{rendered}")


def run_cases(
    cases: list[Case],
    repos: dict[str, dict],
    client,
    log_path: Path,
    *,
    api_key: str = "",
    max_steps: int = DEFAULT_MAX_STEPS,
    echo=print,
) -> list[CaseResult]:
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = RunLog([api_key, getattr(client, "api_key", "")])
    header.add(f"run: {started}")
    header.add(f"model: {getattr(client, 'model', '')}")
    header.add(f"endpoint: {_endpoint(getattr(client, 'base_url', ''))}")
    header.add()

    shown: dict = {}
    results: list[CaseResult] = []
    body = RunLog([api_key, getattr(client, "api_key", "")])
    for case in cases:
        case_log = RunLog([api_key, getattr(client, "api_key", "")])
        shown["staged"] = []
        result = _run_one(case, repos[case.repo], client, case_log, max_steps, shown)
        # System prompt and tools come first in the log, then again only when
        # a later case sends something different.
        for block in shown["staged"]:
            body.add(block)
        if shown["staged"]:
            body.add()
        for line in case_log.lines:
            body.add(line)
        results.append(result)
        echo(f"case {case.id}: {'PASS' if result.passed else 'FAIL'}  ({case.purpose})")

    passed = sum(1 for r in results if r.passed)
    summary = f"cases passed: {passed} of {len(results)}"
    body.add(summary)
    echo(summary)
    Path(log_path).write_text(header.text() + body.text(), encoding="utf-8")
    return results
