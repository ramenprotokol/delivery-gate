from __future__ import annotations

import json
import subprocess

import pytest

from delivery_gate import cli
from delivery_gate.cases import (
    CasesError,
    build_repo,
    load_cases,
    load_repos,
    run_cases,
)
from delivery_gate.llm import ChatReply, LlmError, ToolCall

SECRET = "sk-test-secret-123"

RELEASE_YAML = (
    'version: "1.4.0"\n'
    "attestations:\n"
    "  rollback_tested: {answer: true, by: Eng}\n"
    "  oncall_notified: {answer: true, by: Eng}\n"
    "  approver_signed_off: {answer: true, by: Eng}\n"
    "  monitoring_reviewed: {answer: true, by: Eng}\n"
)
PYPROJECT = '[project]\nname="x"\nversion="1.4.0"\ndependencies=["PyYAML==6.0.2"]\n'

REPOS = {
    "good": {
        "files": {
            "release.yaml": RELEASE_YAML,
            "pyproject.toml": PYPROJECT,
            "CHANGELOG.md": "## [1.4.0]\n- things\n",
        },
        "tags": ["v1.4.0"],
    },
    "nochangelog": {
        "files": {
            "release.yaml": RELEASE_YAML,
            "pyproject.toml": PYPROJECT,
            "CHANGELOG.md": "# Changelog\n",
        },
        "tags": ["v1.4.0"],
    },
}


class FakeClient:
    model = "fake-model"
    base_url = "https://llm.example.invalid/api/v1"
    api_key = SECRET

    def __init__(self, scripts):
        # one list of replies per case, consumed in order
        self.scripts = [list(s) for s in scripts]
        self.index = -1
        self.pending = None
        self.requests = []

    def chat(self, messages, tools=None, model=None):
        first = len(messages) == 2
        if first:
            self.index += 1
            self.pending = self.scripts[self.index]
        self.requests.append((messages, tools))
        reply = self.pending.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _call(name, arguments=None, text=""):
    return ChatReply(content=text, tool_calls=[ToolCall("c1", name, arguments or {})])


def _finish(summary, findings=()):
    return _call("finish", {"summary": summary, "findings": list(findings)})


def _case(i, repo, expect, ci="success", purpose="p"):
    return {
        "id": i,
        "purpose": purpose,
        "command": f"delivery-gate investigate --ci-status {ci}",
        "repo": repo,
        "ci_status": ci,
        "expect": expect,
    }


def _write(tmp_path, cases, repos=REPOS):
    cases_file = tmp_path / "cases.jsonl"
    cases_file.write_text("\n".join(json.dumps(c) for c in cases) + "\n")
    repos_file = tmp_path / "repos.json"
    repos_file.write_text(json.dumps(repos))
    return cases_file, repos_file


def _run(tmp_path, cases, client, repos=REPOS):
    cases_file, repos_file = _write(tmp_path, cases, repos)
    loaded_repos = load_repos(repos_file)
    loaded = load_cases(cases_file, loaded_repos)
    log = tmp_path / "run.log"
    out = []
    results = run_cases(loaded, loaded_repos, client, log, api_key=SECRET, echo=out.append)
    return results, log.read_text(), out


def _git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=path, capture_output=True, text=True, check=True
    ).stdout


def test_repo_builder_commits_tags_dirties_and_adds_untracked(tmp_path):
    spec = {
        "files": {"a.txt": "one\n", "sub/b.txt": "two\n"},
        "tags": ["v1", "v1.0"],
        "uncommitted": {"a.txt": "changed\n"},
        "untracked": {"new.txt": "x\n"},
    }
    build_repo(spec, tmp_path / "r")
    root = tmp_path / "r"
    assert sorted(_git(root, "tag", "--points-at", "HEAD").split()) == ["v1", "v1.0"]
    status = _git(root, "status", "--porcelain")
    assert " M a.txt" in status
    assert "?? new.txt" in status
    assert _git(root, "log", "--format=%an <%ae> %aI").strip() == (
        "Mock <mock@example.invalid> 2020-01-01T00:00:00Z"
    )
    assert _git(root, "rev-list", "--count", "HEAD").strip() == "1"


def test_repo_builder_is_reproducible_and_allows_empty_spec(tmp_path):
    spec = {"files": {"a.txt": "one\n"}}
    build_repo(spec, tmp_path / "x")
    build_repo(spec, tmp_path / "y")
    assert _git(tmp_path / "x", "rev-parse", "HEAD") == _git(tmp_path / "y", "rev-parse", "HEAD")
    build_repo({}, tmp_path / "empty")
    assert _git(tmp_path / "empty", "status", "--porcelain") == ""


def test_repo_file_paths_cannot_escape(tmp_path):
    bad = tmp_path / "repos.json"
    bad.write_text(json.dumps({"r": {"files": {"../evil": "x"}}}))
    with pytest.raises(CasesError):
        load_repos(bad)


def test_passing_case(tmp_path):
    client = FakeClient([[_call("run_checks", text="Starting."), _finish("Release is ready.")]])
    cases = [_case(1, "good", {"decision": "GO", "must_call": ["run_checks"]})]
    results, log, out = _run(tmp_path, cases, client)
    assert results[0].passed
    assert "result: PASS" in log
    assert out[0].startswith("case 1: PASS")
    assert out[-1] == "cases passed: 1 of 1"
    assert 'model: "Starting."' in log


def test_failing_case_gives_the_right_reasons(tmp_path):
    client = FakeClient(
        [
            [
                _call("run_checks"),
                _finish("Blocked.", [{"check_id": "ci_status", "explanation": "CI failed"}]),
            ]
        ]
    )
    cases = [
        _case(
            1,
            "nochangelog",
            {
                "decision": "GO",
                "findings_mention": ["zebra"],
                "findings_not_mention": ["ci_status"],
                "must_call": ["read_file"],
                "max_findings": 0,
            },
            ci="failure",
        )
    ]
    results, log, _ = _run(tmp_path, cases, client)
    assert not results[0].passed
    reasons = results[0].reasons
    assert "decision was NO-GO, expected GO" in reasons
    assert 'findings never mention "zebra"' in reasons
    assert 'findings mention "ci_status" but should not' in reasons
    assert "never called read_file" in reasons
    assert any(r.startswith("2 findings") or "findings, expected at most 0" in r for r in reasons)
    assert "result: FAIL" in log
    assert 'findings never mention "zebra"' in log


def test_must_not_call(tmp_path):
    client = FakeClient([[_call("read_file", {"path": "CHANGELOG.md"}), _finish("ok")]])
    cases = [_case(1, "good", {"must_not_call": ["read_file"]})]
    results, log, _ = _run(tmp_path, cases, client)
    assert results[0].reasons == ["called read_file but should not have"]
    assert "tool call: read_file" in log
    assert "## [1.4.0]" in log


def test_findings_mention_is_case_insensitive_and_reads_summary(tmp_path):
    client = FakeClient([[_finish("The changelog is missing a heading.")]])
    cases = [_case(1, "good", {"findings_mention": ["CHANGELOG"]})]
    results, _, _ = _run(tmp_path, cases, client)
    assert results[0].passed


def test_api_error_mid_run_fails_that_case_and_the_run_continues(tmp_path):
    client = FakeClient(
        [
            [_call("run_checks"), LlmError(f"Model API returned HTTP 500: boom {SECRET}")],
            [_finish("Fine.")],
        ]
    )
    cases = [_case(1, "good", {"decision": "GO"}), _case(2, "good", {"decision": "GO"})]
    results, log, out = _run(tmp_path, cases, client)
    assert [r.passed for r in results] == [False, True]
    assert "model API error: Model API returned HTTP 500" in results[0].reasons[0]
    assert SECRET not in log
    assert SECRET not in "".join(results[0].reasons)
    assert out[-1] == "cases passed: 1 of 2"


def test_crash_in_one_case_is_a_fail_and_run_continues(tmp_path):
    repos = {**REPOS, "broken": {"files": {"README.md": "no manifest here\n"}}}
    client = FakeClient([[_finish("Fine.")]])
    cases = [_case(1, "broken", {}), _case(2, "good", {"decision": "GO"})]
    results, log, _ = _run(tmp_path, cases, client, repos)
    assert not results[0].passed
    assert results[0].reasons[0].startswith("crashed:")
    assert results[1].passed
    assert "cases passed: 1 of 2" in log


def test_log_contents(tmp_path):
    client = FakeClient([[_call("run_checks"), _finish("All good.")], [_finish("Again.")]])
    cases = [_case(1, "good", {}, purpose="Bug being fixed"), _case(2, "good", {})]
    _, log, _ = _run(tmp_path, cases, client)
    lines = log.splitlines()
    assert lines[0].startswith("run: 20")
    assert "model: fake-model" in lines
    assert "endpoint: https://llm.example.invalid" in lines
    assert "system prompt:" in lines
    assert "release-gate investigator" in log
    assert '"name": "run_checks"' in log
    assert "case 1  (Bug being fixed)" in lines
    assert "  user: delivery-gate investigate --ci-status success   [repo good]" in lines
    assert "  tool call: run_checks({}) -> " in log
    assert "  brief: GO | All good. | findings: 0" in lines
    assert log.rstrip().endswith("cases passed: 2 of 2")
    assert "/private" not in log and "delivery-gate-case-" not in log
    assert "/api/v1" not in log


def test_system_prompt_and_tools_printed_once_when_unchanged(tmp_path):
    client = FakeClient([[_finish("a")], [_finish("b")]])
    cases = [_case(1, "good", {}), _case(2, "good", {})]
    _, log, _ = _run(tmp_path, cases, client)
    assert log.count("system prompt:") == 1
    assert log.count("\ntools:\n") == 1


def test_system_prompt_reprinted_when_it_changes(tmp_path):
    client = FakeClient([[_finish("a")], [_finish("b")]])
    cases = [_case(1, "good", {}, ci="success"), _case(2, "good", {}, ci="failure")]
    _, log, _ = _run(tmp_path, cases, client)
    assert log.count("system prompt:") == 2
    assert "CI status passed in: 'failure'" in log


def test_key_never_in_log_even_if_model_or_files_echo_it(tmp_path):
    repos = {
        "leaky": {
            "files": {**REPOS["good"]["files"], "notes.txt": f"token {SECRET}\n"},
            "tags": ["v1.4.0"],
        }
    }
    client = FakeClient(
        [[_call("read_file", {"path": "notes.txt"}, text=f"key is {SECRET}"), _finish(f"{SECRET}")]]
    )
    _, log, _ = _run(tmp_path, [_case(1, "leaky", {})], client, repos)
    assert SECRET not in log
    assert "***" in log


def test_load_cases_rejects_bad_input(tmp_path):
    repos = {"r": {}}
    for bad in (
        {"id": 1, "repo": "nope"},
        {"id": 1, "repo": "r", "expect": {"must_call": ["not_a_tool"]}},
        {"id": 1, "repo": "r", "expect": {"decision": "MAYBE"}},
        {"id": 1, "repo": "r", "expect": {"surprise": 1}},
    ):
        f = tmp_path / "c.jsonl"
        f.write_text(json.dumps(bad) + "\n")
        with pytest.raises(CasesError):
            load_cases(f, repos)


def test_cli_end_to_end_with_fake_client(tmp_path, monkeypatch, capsys):
    cases_file, repos_file = _write(
        tmp_path, [_case(1, "good", {"decision": "GO"}), _case(2, "good", {"decision": "NO-GO"})]
    )
    client = FakeClient([[_finish("ok")], [_finish("ok")]])
    monkeypatch.setattr(cli.LlmClient, "from_env", classmethod(lambda cls, model=None: client))
    log = tmp_path / "out" / "run.log"
    log.parent.mkdir()
    code = cli.main(
        ["cases", "--cases", str(cases_file), "--repos", str(repos_file), "--log", str(log)]
    )
    assert code == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("case 1: PASS")
    assert out[1].startswith("case 2: FAIL")
    assert out[-1] == "cases passed: 1 of 2"
    assert "cases passed: 1 of 2" in log.read_text()
    assert SECRET not in log.read_text() + "".join(out)


def test_cli_usage_errors_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DELIVERY_GATE_LLM_MODEL", "m")
    monkeypatch.setenv("DELIVERY_GATE_LLM_API_KEY", SECRET)
    missing = tmp_path / "missing.json"
    code = cli.main(
        ["cases", "--cases", str(missing), "--repos", str(missing), "--log", str(tmp_path / "l")]
    )
    assert code == 2
    assert SECRET not in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        cli.main(["cases", "--cases", "x"])
    assert exc.value.code == 2
