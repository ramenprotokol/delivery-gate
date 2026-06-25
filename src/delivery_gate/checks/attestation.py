from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status

REQUIRED_ATTESTATIONS: list[tuple[str, str]] = [
    ("rollback_tested", "Rollback procedure tested"),
    ("oncall_notified", "On-call engineer notified"),
    ("approver_signed_off", "Named approver signed off"),
    ("monitoring_reviewed", "Monitoring and alerts reviewed"),
]


class AttestationCheck(Check):
    kind = Kind.ATTESTED

    def __init__(self, key: str, label: str):
        self.id = key
        self.label = label

    def run(self, context: Context) -> Result:
        na = context.manifest.not_applicable.get(self.id)
        if na is not None:
            return Result(self.id, self.label, Status.NA, self.kind, f"Marked not applicable: {na}")
        att = context.manifest.attestations.get(self.id)
        if att is None:
            return Result(
                self.id,
                self.label,
                Status.FAIL,
                self.kind,
                "No attestation provided in release.yaml.",
            )
        if not att.answer:
            return Result(
                self.id, self.label, Status.FAIL, self.kind, "Attested as not done (answer: false)."
            )
        if not att.by:
            return Result(
                self.id,
                self.label,
                Status.FAIL,
                self.kind,
                "Attestation has no attester ('by' is empty).",
            )
        evidence = f" Evidence: {att.evidence}" if att.evidence else ""
        return Result(
            self.id, self.label, Status.PASS, self.kind, f"Attested by {att.by}.{evidence}"
        )


def build_attestation_checks() -> list[Check]:
    return [AttestationCheck(key, label) for key, label in REQUIRED_ATTESTATIONS]
