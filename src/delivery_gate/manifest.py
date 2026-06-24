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
    if not version:
        raise ManifestError(f"{path} is missing required field 'version'.")

    attestations: dict[str, Attestation] = {}
    for key, val in (raw.get("attestations") or {}).items():
        val = val or {}
        attestations[key] = Attestation(
            key=key,
            answer=bool(val.get("answer", False)),
            by=val.get("by"),
            evidence=val.get("evidence"),
        )

    not_applicable = dict(raw.get("not_applicable") or {})
    return Manifest(
        version=str(version),
        attestations=attestations,
        not_applicable=not_applicable,
    )
