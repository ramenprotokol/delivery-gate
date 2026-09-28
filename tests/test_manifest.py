from pathlib import Path

import pytest

from delivery_gate.manifest import Attestation, Manifest, ManifestError, load


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "release.yaml"
    p.write_text(text)
    return p


def test_loads_valid_manifest(tmp_path):
    p = _write(
        tmp_path,
        """
version: "0.1.0"
attestations:
  rollback_tested:
    answer: true
    by: "A. Engineer"
    evidence: "https://example/run"
not_applicable:
  feature_flags: "No flags this release."
""",
    )
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


def test_attestation_value_not_a_mapping_raises_cleanly(tmp_path):
    # A typo'd manifest must fail with ManifestError, not an AttributeError traceback.
    p = _write(tmp_path, 'version: "1.0.0"\nattestations:\n  rollback_tested: "yes"\n')
    with pytest.raises(ManifestError, match="rollback_tested"):
        load(p)


def test_attestations_not_a_mapping_raises_cleanly(tmp_path):
    p = _write(tmp_path, 'version: "1.0.0"\nattestations:\n  - rollback_tested\n')
    with pytest.raises(ManifestError, match="attestations"):
        load(p)


def test_not_applicable_not_a_mapping_raises_cleanly(tmp_path):
    p = _write(tmp_path, 'version: "1.0.0"\nnot_applicable:\n  - feature_flags\n')
    with pytest.raises(ManifestError, match="not_applicable"):
        load(p)


@pytest.mark.parametrize("answer", ['"false"', '"no"', '"true"', "pending", "1", "0", "[true]"])
def test_non_boolean_answer_is_rejected(tmp_path, answer):
    # A quoted "false" is a non-empty string, and bool("false") is True. That
    # used to turn an explicit "not done" into a PASS. Only YAML booleans count.
    p = _write(
        tmp_path,
        f'version: "1.0.0"\nattestations:\n  rollback_tested: {{answer: {answer}, by: Eng}}\n',
    )
    with pytest.raises(ManifestError, match="rollback_tested"):
        load(p)


def test_boolean_answers_still_load(tmp_path):
    p = _write(
        tmp_path,
        'version: "1.0.0"\nattestations:\n'
        "  rollback_tested: {answer: true, by: Eng}\n"
        "  oncall_notified: {answer: false, by: Eng}\n",
    )
    m = load(p)
    assert m.attestations["rollback_tested"].answer is True
    assert m.attestations["oncall_notified"].answer is False


def test_blank_attester_counts_as_missing(tmp_path):
    p = _write(
        tmp_path, 'version: "1.0.0"\nattestations:\n  rollback_tested: {answer: true, by: "   "}\n'
    )
    assert load(p).attestations["rollback_tested"].by is None


def test_non_string_attester_is_rejected(tmp_path):
    p = _write(
        tmp_path, 'version: "1.0.0"\nattestations:\n  rollback_tested: {answer: true, by: [Eng]}\n'
    )
    with pytest.raises(ManifestError, match="by"):
        load(p)
