from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status


class CiStatusCheck(Check):
    id = "ci_status"
    label = "Tests passed in CI"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        status = (context.ci_status or "").strip().lower()
        if status == "success":
            return Result(self.id, self.label, Status.PASS, self.kind,
                          "CI reported success.")
        if not status:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "CI status unknown (none provided) — treating as a fail.")
        return Result(self.id, self.label, Status.FAIL, self.kind,
                      f"CI status is '{status}', not 'success'.")
