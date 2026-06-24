from pathlib import Path
import pytest
from delivery_gate.manifest import load, Manifest, Attestation, ManifestError


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "release.yaml"
    p.write_text(text)
    return p


def test_loads_valid_manifest(tmp_path):
    p = _write(tmp_path, """
version: "0.1.0"
attestations:
  rollback_tested:
    answer: true
    by: "A. Engineer"
    evidence: "https://example/run"
not_applicable:
  feature_flags: "No flags this release."
""")
    m = load(p)
    assert isinstance(m, Manifest)
    assert m.version == "0.1.0"
    a = m.attestations["rollback_tested"]
    assert a == Attestation("rollback_tested", True, "A. Engineer", "https://example/run")
    assert m.not_applicable["feature_flags"] == "No flags this release."


def test_missing_file_raises_manifest_error(tmp_path):
    with pytest.raises(ManifestError, match="not found"):
        load(tmp_path / "nope.yaml")


def test_missing_version_raises(tmp_path):
    p = _write(tmp_path, "attestations: {}\n")
    with pytest.raises(ManifestError, match="version"):
        load(p)


def test_bad_yaml_raises(tmp_path):
    p = _write(tmp_path, "version: [unterminated\n")
    with pytest.raises(ManifestError):
        load(p)
