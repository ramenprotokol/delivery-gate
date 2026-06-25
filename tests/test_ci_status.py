from delivery_gate.base import Status
from delivery_gate.checks.ci_status import CiStatusCheck


def ctx(ci_status):
    from delivery_gate.base import Context
    from delivery_gate.manifest import Manifest

    m = Manifest(version="0.1.0", attestations={}, not_applicable={})
    return Context(repo_path=None, manifest=m, ci_status=ci_status, git=None)


def test_pass_on_success():
    assert CiStatusCheck().run(ctx("success")).status is Status.PASS


def test_pass_case_insensitive():
    assert CiStatusCheck().run(ctx("SUCCESS")).status is Status.PASS


def test_fail_on_failure():
    assert CiStatusCheck().run(ctx("failure")).status is Status.FAIL


def test_fail_on_unknown_none():
    r = CiStatusCheck().run(ctx(None))
    assert r.status is Status.FAIL
    assert "unknown" in r.message.lower()
