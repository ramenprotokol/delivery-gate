from delivery_gate.base import Kind, Result, Status
from delivery_gate.runner import build_checks, decide


def test_build_checks_has_four_auto_plus_attestations():
    checks = build_checks()
    auto = [c for c in checks if c.kind is Kind.AUTO]
    attested = [c for c in checks if c.kind is Kind.ATTESTED]
    assert len(auto) == 4
    assert len(attested) == 4


def _r(status):
    return Result("x", "X", status, Kind.AUTO, "")


def test_decide_go_when_no_fail():
    assert decide([_r(Status.PASS), _r(Status.NA)]) is True


def test_decide_nogo_when_any_fail():
    assert decide([_r(Status.PASS), _r(Status.FAIL)]) is False
