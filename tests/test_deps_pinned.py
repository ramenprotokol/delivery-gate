from delivery_gate.base import Status
from delivery_gate.checks.deps_pinned import DepsPinnedCheck


def ctx(tmp_path):
    from delivery_gate.base import Context
    from delivery_gate.manifest import Manifest
    m = Manifest(version="0.1.0", attestations={}, not_applicable={})
    return Context(repo_path=tmp_path, manifest=m, ci_status=None, git=None)


def test_pass_when_all_pinned(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.1.0"\ndependencies=["PyYAML==6.0.2","rich==13.9.0"]\n'
    )
    assert DepsPinnedCheck().run(ctx(tmp_path)).status is Status.PASS


def test_fail_when_unpinned(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.1.0"\ndependencies=["PyYAML>=6","rich==13.9.0"]\n'
    )
    r = DepsPinnedCheck().run(ctx(tmp_path))
    assert r.status is Status.FAIL
    assert "PyYAML" in r.message


def test_pass_when_no_deps(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0.1.0"\n')
    r = DepsPinnedCheck().run(ctx(tmp_path))
    assert r.status is Status.PASS


def test_fail_when_no_pyproject(tmp_path):
    r = DepsPinnedCheck().run(ctx(tmp_path))
    assert r.status is Status.FAIL
    assert "pyproject.toml" in r.message
