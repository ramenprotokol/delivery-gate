from pathlib import Path

from delivery_gate.adapters.git import GitAdapter


def make_runner(responses):
    calls = []

    def runner(args):
        calls.append(tuple(args))
        key = " ".join(args)
        return responses.get(key, "")

    runner.calls = calls
    return runner


def test_is_clean_true_when_porcelain_empty():
    runner = make_runner({"status --porcelain": ""})
    g = GitAdapter(Path("."), runner=runner)
    assert g.is_clean() is True


def test_is_clean_false_when_changes_present():
    runner = make_runner({"status --porcelain": " M file.py\n"})
    g = GitAdapter(Path("."), runner=runner)
    assert g.is_clean() is False


def test_tag_at_head_returns_tag():
    runner = make_runner({"tag --points-at HEAD": "v0.1.0\n"})
    g = GitAdapter(Path("."), runner=runner)
    assert g.tag_at_head() == "v0.1.0"


def test_tag_at_head_none_when_no_tag():
    runner = make_runner({"tag --points-at HEAD": "\n"})
    g = GitAdapter(Path("."), runner=runner)
    assert g.tag_at_head() is None
