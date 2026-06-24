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
