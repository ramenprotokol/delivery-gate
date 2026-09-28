from pathlib import Path

import delivery_gate.cli as climod

FIX = Path(__file__).parent / "fixtures"


class FakeGit:
    def __init__(self, *a, **k):
        pass

    def is_clean(self):
        return True

    def tag_at_head(self):
        return "v0.1.0"


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


def test_dirty_tree_is_nogo_even_when_git_status_errors(tmp_path):
    # Real git, no fakes: a tagged pass_repo copy with an uncommitted change and
    # a corrupt index (so `git status` errors). The gate must say NO-GO.
    import shutil
    import subprocess

    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            + ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    shutil.copytree(FIX / "pass_repo", tmp_path, dirs_exist_ok=True)
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "release")
    git("tag", "v0.1.0")
    (tmp_path / "unreviewed.py").write_text("print('not in the release')\n")
    (tmp_path / ".git" / "index").write_bytes(b"garbage")

    rc = climod.main(["check", "--repo", str(tmp_path), "--ci-status", "success"])
    assert rc == 1
