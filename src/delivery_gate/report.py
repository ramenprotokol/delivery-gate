from __future__ import annotations

import json

from delivery_gate.base import Result, Status

_SYMBOL = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.NA: "NA  "}


def render_text(results: list[Result], go: bool) -> str:
    lines = ["delivery-gate report", "=" * 40]
    for r in results:
        lines.append(f"[{r.kind.value}] {_SYMBOL[r.status]}  {r.label} — {r.message}")
    fails = [r for r in results if r.status is Status.FAIL]
    if not go and fails:
        lines.append("")
        lines.append("Hold reasons (NO-GO):")
        for r in fails:
            lines.append(f"  - {r.label}: {r.message}")
    lines.append("")
    lines.append("Decision: " + ("GO" if go else "NO-GO"))
    return "\n".join(lines)


def render_json(results: list[Result], go: bool) -> str:
    payload = {
        "decision": "GO" if go else "NO-GO",
        "results": [
            {
                "check_id": r.check_id,
                "label": r.label,
                "status": r.status.value,
                "kind": r.kind.value,
                "message": r.message,
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2)
