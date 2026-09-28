from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class ManifestError(Exception):
    """Raised when release.yaml is missing, malformed, or incomplete."""


@dataclass(frozen=True)
class Attestation:
    key: str
    answer: bool
    by: str | None
    evidence: str | None


@dataclass(frozen=True)
class Manifest:
    version: str
    attestations: dict[str, Attestation]
    not_applicable: dict[str, str]


def load(path: Path) -> Manifest:
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"Release manifest not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"Could not parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path} must be a YAML mapping at the top level.")

    version = raw.get("version")
    if version is None or version == "":
        raise ManifestError(f"{path} is missing required field 'version'.")
    if not isinstance(version, str) or not version.strip():
        raise ManifestError(
            f"{path}: 'version' must be a quoted string such as \"1.2.3\", "
            f"got {type(version).__name__}."
        )

    raw_attestations = raw.get("attestations") or {}
    if not isinstance(raw_attestations, dict):
        raise ManifestError(
            f"{path}: 'attestations' must be a mapping of name -> {{answer, by, evidence}}, "
            f"got {type(raw_attestations).__name__}."
        )

    attestations: dict[str, Attestation] = {}
    for key, val in raw_attestations.items():
        val = val or {}
        if not isinstance(val, dict):
            raise ManifestError(
                f"{path}: attestation '{key}' must be a mapping with an 'answer' field, "
                f"got {type(val).__name__}."
            )
        answer = val.get("answer", False)
        if not isinstance(answer, bool):
            raise ManifestError(
                f"{path}: attestation '{key}' needs 'answer: true' or 'answer: false' "
                f"(an unquoted YAML boolean), got {type(answer).__name__}."
            )
        by = val.get("by")
        if by is not None and not isinstance(by, str):
            raise ManifestError(
                f"{path}: attestation '{key}' field 'by' must be a name, got {type(by).__name__}."
            )
        evidence = val.get("evidence")
        if evidence is not None and not isinstance(evidence, str):
            raise ManifestError(
                f"{path}: attestation '{key}' field 'evidence' must be text, "
                f"got {type(evidence).__name__}."
            )
        attestations[key] = Attestation(
            key=key,
            answer=answer,
            by=(by or "").strip() or None,
            evidence=evidence,
        )

    raw_na = raw.get("not_applicable") or {}
    if not isinstance(raw_na, dict):
        raise ManifestError(
            f"{path}: 'not_applicable' must be a mapping of name -> reason, "
            f"got {type(raw_na).__name__}."
        )
    for key, reason in raw_na.items():
        if not isinstance(reason, str) or not reason.strip():
            raise ManifestError(
                f"{path}: not_applicable '{key}' needs a written reason (a non-empty string)."
            )
    not_applicable = dict(raw_na)
    return Manifest(
        version=str(version),
        attestations=attestations,
        not_applicable=not_applicable,
    )
