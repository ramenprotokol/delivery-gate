import json

from delivery_gate.base import Kind, Result, Status
from delivery_gate.report import render_json, render_text

RESULTS = [
    Result("changelog", "CHANGELOG updated", Status.PASS, Kind.AUTO, "ok"),
    Result("rollback_tested", "Rollback tested", Status.FAIL, Kind.ATTESTED, "missing"),
    Result("oncall_notified", "On-call notified", Status.NA, Kind.ATTESTED, "n/a"),
]


def test_text_lists_results_and_decision():
    out = render_text(RESULTS, go=False)
    assert "[AUTO]" in out and "[ATTESTED]" in out
    assert "NO-GO" in out
    assert "Rollback tested" in out  # hold reason listed


def test_text_go_line_when_go():
    out = render_text([RESULTS[0]], go=True)
    assert "GO" in out and "NO-GO" not in out


def test_json_shape():
    out = render_json(RESULTS, go=False)
    data = json.loads(out)
    assert data["decision"] == "NO-GO"
    assert len(data["results"]) == 3
    assert data["results"][0]["check_id"] == "changelog"
    assert data["results"][0]["status"] == "PASS"
