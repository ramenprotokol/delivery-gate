from pathlib import Path

from delivery_gate.cli import main


def _passing_repo(tmp_path: Path):
    (tmp_path / "CHANGELOG.md").write_text("## 0.1.0\n- ok\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.1.0"\ndependencies=["PyYAML==6.0.2"]\n'
    )
    (tmp_path / "release.yaml").write_text(
        'version: "0.1.0"\n'
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

    monkeypatch.setattr(climod, "GitAdapter", _FakeGit)
    rc = main(["check", "--repo", str(repo), "--ci-status", "success"])
    assert rc == 0


def test_nogo_returns_one(tmp_path, monkeypatch):
    repo = _passing_repo(tmp_path)
    import delivery_gate.cli as climod

    monkeypatch.setattr(climod, "GitAdapter", _FakeGit)
    rc = main(["check", "--repo", str(repo), "--ci-status", "failure"])
    assert rc == 1


def test_missing_manifest_returns_two(tmp_path, capsys):
    rc = main(["check", "--repo", str(tmp_path), "--ci-status", "success"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_module_is_runnable_via_dash_m():
    # Guards the `python -m delivery_gate.cli` entrypoint: with no subcommand,
    # argparse must exit 2 (proving main() actually executed, not a silent no-op).
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "delivery_gate.cli"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "usage" in (proc.stdout + proc.stderr).lower()


class _FakeGit:
    def __init__(self, *a, **k):
        pass

    def is_repo_root(self):
        return True

    def repo_root(self):
        return Path(".")

    def is_clean(self):
        return True

    def tag_at_head(self):
        return "v0.1.0"

    def tags_at_head(self):
        return ["v0.1.0"]

    def status_porcelain(self):
        return ""


def _fake_client(replies):
    from delivery_gate.llm import ChatReply, ToolCall

    class FakeClient:
        model = "flash-model"

        def chat(self, messages, tools=None, model=None):
            if not replies:
                return ChatReply(
                    content="done",
                    tool_calls=[ToolCall(id="f", name="finish", arguments={"summary": "done"})],
                )
            return replies.pop(0)

    return FakeClient()


def _install_client(monkeypatch, replies):
    import delivery_gate.cli as climod

    monkeypatch.setattr(climod, "GitAdapter", _FakeGit)
    monkeypatch.setattr(climod.LlmClient, "from_env", lambda **k: _fake_client(replies))


def test_investigate_nogo_returns_one(tmp_path, monkeypatch, capsys):
    from delivery_gate.llm import ChatReply, ToolCall

    repo = _passing_repo(tmp_path)
    _install_client(
        monkeypatch,
        [
            ChatReply(
                content="",
                tool_calls=[
                    ToolCall(id="f", name="finish", arguments={"summary": "Blocked on CI."})
                ],
            )
        ],
    )
    rc = main(["investigate", "--repo", str(repo), "--ci-status", "failure"])
    assert rc == 1
    assert "Decision: NO-GO" in capsys.readouterr().out


def test_investigate_go_returns_zero(tmp_path, monkeypatch, capsys):
    from delivery_gate.llm import ChatReply, ToolCall

    repo = _passing_repo(tmp_path)
    _install_client(
        monkeypatch,
        [
            ChatReply(
                content="",
                tool_calls=[ToolCall(id="f", name="finish", arguments={"summary": "Ready."})],
            )
        ],
    )
    rc = main(["investigate", "--repo", str(repo), "--ci-status", "success"])
    assert rc == 0
    assert "Decision: GO" in capsys.readouterr().out


def test_investigate_json_output(tmp_path, monkeypatch, capsys):
    import json

    from delivery_gate.llm import ChatReply, ToolCall

    repo = _passing_repo(tmp_path)
    _install_client(
        monkeypatch,
        [
            ChatReply(
                content="",
                tool_calls=[ToolCall(id="f", name="finish", arguments={"summary": "Blocked."})],
            )
        ],
    )
    rc = main(["investigate", "--repo", str(repo), "--ci-status", "failure", "--json"])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["decision"] == "NO-GO"


def test_investigate_trace_goes_to_stderr_and_keeps_json_clean(tmp_path, monkeypatch, capsys):
    import json

    from delivery_gate.llm import ChatReply, ToolCall

    repo = _passing_repo(tmp_path)
    _install_client(
        monkeypatch,
        [
            ChatReply(content="", tool_calls=[ToolCall(id="c1", name="run_checks", arguments={})]),
            ChatReply(
                content="",
                tool_calls=[ToolCall(id="f", name="finish", arguments={"summary": "Blocked."})],
            ),
        ],
    )
    rc = main(["investigate", "--repo", str(repo), "--ci-status", "failure", "--json", "--trace"])
    captured = capsys.readouterr()
    assert rc == 1
    payload = json.loads(captured.out)
    assert payload["decision"] == "NO-GO"
    assert "[trace] flash-model: run_checks(" in captured.err
    assert "[trace] flash-model: finish(" in captured.err


def test_investigate_brief_model_flag_reaches_the_client(tmp_path, monkeypatch, capsys):
    import delivery_gate.cli as climod
    from delivery_gate.llm import ChatReply, ToolCall

    repo = _passing_repo(tmp_path)
    monkeypatch.setattr(climod, "GitAdapter", _FakeGit)

    seen = []

    class FakeClient:
        model = "flash-model"

        def chat(self, messages, tools=None, model=None):
            seen.append(model)
            if tools is None:  # the brief call has no tools
                return ChatReply(content="Big-model brief.", tool_calls=[])
            return ChatReply(
                content="",
                tool_calls=[ToolCall(id="f", name="finish", arguments={"summary": "Draft."})],
            )

    monkeypatch.setattr(climod.LlmClient, "from_env", lambda **k: FakeClient())
    rc = main(
        [
            "investigate",
            "--repo",
            str(repo),
            "--ci-status",
            "failure",
            "--brief-model",
            "big-model",
        ]
    )
    assert rc == 1
    assert "Big-model brief." in capsys.readouterr().out
    assert seen == [None, "big-model"]


def test_investigate_llm_error_returns_two(tmp_path, monkeypatch, capsys):
    from delivery_gate.llm import LlmError

    repo = _passing_repo(tmp_path)
    import delivery_gate.cli as climod

    monkeypatch.setattr(climod, "GitAdapter", _FakeGit)

    def boom(**k):
        raise LlmError("No API key set. Set DELIVERY_GATE_LLM_API_KEY")

    monkeypatch.setattr(climod.LlmClient, "from_env", boom)
    rc = main(["investigate", "--repo", str(repo), "--ci-status", "success"])
    assert rc == 2
    assert "DELIVERY_GATE_LLM_API_KEY" in capsys.readouterr().err


def test_investigate_dead_api_still_prints_the_anchored_decision(tmp_path, monkeypatch, capsys):
    # A model API that cannot be reached is not "could not run": the checks ran
    # fine, so the anchored decision must still be printed, with a cut-off note.
    import delivery_gate.cli as climod
    from delivery_gate.llm import LlmError

    repo = _passing_repo(tmp_path)
    monkeypatch.setattr(climod, "GitAdapter", _FakeGit)

    class DeadClient:
        model = "flash-model"

        def chat(self, messages, tools=None, model=None):
            raise LlmError("Could not reach the model API: [Errno 61] Connection refused")

    monkeypatch.setattr(climod.LlmClient, "from_env", lambda **k: DeadClient())
    rc = main(["investigate", "--repo", str(repo), "--ci-status", "failure"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "Decision: NO-GO" in out
    assert "cut off" in out


def test_investigate_missing_manifest_returns_two(tmp_path, capsys):
    rc = main(["investigate", "--repo", str(tmp_path), "--ci-status", "success"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err
