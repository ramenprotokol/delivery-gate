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
