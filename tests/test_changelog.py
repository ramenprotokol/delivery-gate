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


def _run(tmp_path, version, text):
    (tmp_path / "CHANGELOG.md").write_text(text)
    return ChangelogCheck().run(ctx(tmp_path, version))


def test_fail_when_version_only_mentioned_in_prose(tmp_path):
    # The fail_repo fixture says "(no 0.1.0 entry on purpose)". A bare substring
    # match read that as an entry and passed.
    text = "## 0.0.9 - 2026-01-01\n- old entry (no 0.1.0 entry on purpose)\n"
    assert _run(tmp_path, "0.1.0", text).status is Status.FAIL


def test_fail_when_version_only_in_a_link_reference(tmp_path):
    text = "## 0.0.9\n\n[0.1.0]: https://example.invalid/compare/v0.0.9...v0.1.0\n"
    assert _run(tmp_path, "0.1.0", text).status is Status.FAIL


def test_fail_when_version_is_a_prefix_of_another(tmp_path):
    assert _run(tmp_path, "1.0", "## 1.0.5\n- x\n").status is Status.FAIL
    assert _run(tmp_path, "0.1.0", "## 10.1.0\n- x\n").status is Status.FAIL
    assert _run(tmp_path, "1.2.3", "## 1.2.3-rc1\n- x\n").status is Status.FAIL


def test_pass_on_common_heading_styles(tmp_path):
    for heading in (
        "## [0.1.0] - 2026-06-24",
        "## v0.1.0",
        "# 0.1.0",
        "### Version 0.1.0 (2026-06-24)",
    ):
        assert _run(tmp_path, "0.1.0", f"{heading}\n- x\n").status is Status.PASS, heading


def test_pass_when_manifest_version_has_v_prefix(tmp_path):
    assert _run(tmp_path, "v0.1.0", "## [0.1.0]\n- x\n").status is Status.PASS
