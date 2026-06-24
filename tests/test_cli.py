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


def test_module_is_runnable_via_dash_m():
    # Guards the `python -m delivery_gate.cli` entrypoint: with no subcommand,
    # argparse must exit 2 (proving main() actually executed, not a silent no-op).
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "delivery_gate.cli"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "usage" in (proc.stdout + proc.stderr).lower()
