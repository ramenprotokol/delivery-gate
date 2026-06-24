from delivery_gate.base import Status, Kind
from delivery_gate.manifest import Manifest, Attestation
from delivery_gate.checks.attestation import build_attestation_checks, REQUIRED_ATTESTATIONS


def ctx(attestations, not_applicable=None):
    from delivery_gate.base import Context
    m = Manifest(version="0.1.0", attestations=attestations, not_applicable=not_applicable or {})
    return Context(repo_path=None, manifest=m, ci_status=None, git=None)


def run_all(context):
    return {c.id: c.run(context) for c in build_attestation_checks()}


def test_one_check_per_required_item():
    assert len(build_attestation_checks()) == len(REQUIRED_ATTESTATIONS)


def test_pass_when_attested_true_with_by():
    att = {"rollback_tested": Attestation("rollback_tested", True, "Eng", None)}
    res = run_all(ctx(att))["rollback_tested"]
    assert res.status is Status.PASS
    assert res.kind is Kind.ATTESTED


def test_fail_when_answer_false():
    att = {"rollback_tested": Attestation("rollback_tested", False, "Eng", None)}
    assert run_all(ctx(att))["rollback_tested"].status is Status.FAIL


def test_fail_when_missing():
    assert run_all(ctx({}))["rollback_tested"].status is Status.FAIL


def test_fail_when_no_attester():
    att = {"rollback_tested": Attestation("rollback_tested", True, None, None)}
    assert run_all(ctx(att))["rollback_tested"].status is Status.FAIL


def test_na_when_listed_not_applicable():
    res = run_all(ctx({}, not_applicable={"rollback_tested": "No prod deploy."}))["rollback_tested"]
    assert res.status is Status.NA
    assert "No prod deploy." in res.message
