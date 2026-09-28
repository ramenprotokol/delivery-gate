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


def _git(repo, *args):
    import subprocess

    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_default_runner_raises_when_git_fails(tmp_path):
    # Outside any repository `git status` exits non-zero. That must not read as
    # "clean": the gate has to fail closed when it cannot see the tree.
    import pytest

    from delivery_gate.adapters.git import GitError

    g = GitAdapter(tmp_path)
    with pytest.raises(GitError):
        g.is_clean()


def test_dirty_tree_is_not_clean_when_status_errors(tmp_path):
    # Real repo, tagged, then made dirty. Corrupting the index makes `git status`
    # fail while `git tag --points-at HEAD` still works; before the fix this
    # reported a clean tree and let the release through.
    import pytest

    from delivery_gate.adapters.git import GitError

    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "init")
    _git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "a.txt").write_text("changed\n")
    (tmp_path / ".git" / "index").write_bytes(b"garbage")

    g = GitAdapter(tmp_path)
    assert g.tag_at_head() == "v0.1.0"
    with pytest.raises(GitError):
        g.is_clean()
