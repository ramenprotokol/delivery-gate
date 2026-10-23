from pathlib import Path

from delivery_gate.base import Status
from delivery_gate.checks.release_point import ReleasePointCheck


class FakeGit:
    def __init__(self, clean, tag, root="/repo"):
        self._clean, self._tag, self._root = clean, tag, Path(root)

    def is_repo_root(self):
        return True

    def repo_root(self):
        return self._root

    def is_clean(self):
        return self._clean

    def tag_at_head(self):
        return self._tag


class NotRootGit:
    def __init__(self, root="/outer"):
        self._root = Path(root)

    def is_repo_root(self):
        return False

    def repo_root(self):
        return self._root

    def is_clean(self):
        return True

    def tag_at_head(self):
        return "v0.1.0"


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


class BrokenGit:
    def is_repo_root(self):
        return True

    def repo_root(self):
        from delivery_gate.adapters.git import GitError

        raise GitError("git rev-parse --show-toplevel failed: not a repository")

    def is_clean(self):
        from delivery_gate.adapters.git import GitError

        raise GitError("git status --porcelain failed: fatal: index file corrupt")

    def tag_at_head(self):
        return "v0.1.0"


def test_fail_when_git_errors():
    r = ReleasePointCheck().run(ctx("0.1.0", BrokenGit()))
    assert r.status is Status.FAIL
    assert "git" in r.message.lower()


def test_fail_when_repo_is_not_a_git_root():
    # A --repo nested inside another repository must not inherit that repo's
    # cleanliness or tags: the check cannot verify a release point at all.
    r = ReleasePointCheck().run(ctx("0.1.0", NotRootGit(root="/outer")))
    assert r.status is Status.FAIL
    assert "not the root of a git repository" in r.message
    assert "/outer" in r.message
