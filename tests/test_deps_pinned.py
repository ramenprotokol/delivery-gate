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


def _run(tmp_path, toml):
    (tmp_path / "pyproject.toml").write_text(toml)
    return DepsPinnedCheck().run(ctx(tmp_path))


def test_fail_when_only_the_marker_has_double_equals(tmp_path):
    # `sys_platform == 'win32'` is an environment marker, not a version pin.
    r = _run(
        tmp_path,
        '[project]\nname="x"\nversion="1"\n'
        'dependencies=["rich==13.9.0", "pywin32; sys_platform == \'win32\'"]\n',
    )
    assert r.status is Status.FAIL
    assert "pywin32" in r.message


def test_pass_when_pinned_dep_has_a_marker(tmp_path):
    r = _run(
        tmp_path,
        '[project]\nname="x"\nversion="1"\n'
        "dependencies=[\"tomli==2.0.1; python_version < '3.11'\"]\n",
    )
    assert r.status is Status.PASS


def test_fail_on_wildcard_pin(tmp_path):
    r = _run(tmp_path, '[project]\nname="x"\nversion="1"\ndependencies=["rich==13.*"]\n')
    assert r.status is Status.FAIL


def test_fail_when_dependencies_are_dynamic(tmp_path):
    # Deps come from elsewhere (e.g. requirements.txt); nothing was checked.
    r = _run(tmp_path, '[project]\nname="x"\nversion="1"\ndynamic=["dependencies"]\n')
    assert r.status is Status.FAIL


def test_fail_when_no_project_table(tmp_path):
    # e.g. a Poetry project: the gate cannot see the deps, so it must not PASS.
    r = _run(tmp_path, '[tool.poetry.dependencies]\nrequests="^2.0"\n')
    assert r.status is Status.FAIL


def test_fail_when_dependencies_is_not_a_list_of_strings(tmp_path):
    r = _run(tmp_path, '[project]\nname="x"\nversion="1"\ndependencies=["rich==13.9.0", 5]\n')
    assert r.status is Status.FAIL
