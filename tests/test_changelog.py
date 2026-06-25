from delivery_gate.base import Kind, Status
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
