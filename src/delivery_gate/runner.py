from __future__ import annotations

from delivery_gate.base import Check, Context, Result, Status
from delivery_gate.checks.attestation import build_attestation_checks
from delivery_gate.checks.changelog import ChangelogCheck
from delivery_gate.checks.ci_status import CiStatusCheck
from delivery_gate.checks.deps_pinned import DepsPinnedCheck
from delivery_gate.checks.release_point import ReleasePointCheck


def build_checks() -> list[Check]:
    auto: list[Check] = [
        ChangelogCheck(),
        CiStatusCheck(),
        DepsPinnedCheck(),
        ReleasePointCheck(),
    ]
    return auto + build_attestation_checks()


def run_checks(context: Context) -> list[Result]:
    return [check.run(context) for check in build_checks()]


def decide(results: list[Result]) -> bool:
    return not any(r.status is Status.FAIL for r in results)
