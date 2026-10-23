from __future__ import annotations

import json

import pytest

from delivery_gate.adapters.git import GitAdapter
from delivery_gate.base import Context
from delivery_gate.manifest import load
from delivery_gate.tools import _MAX_FILE_BYTES, Toolbox, ToolError


def _context(tmp_path, *, porcelain: str = "", tags: str = "v0.1.0\n", root: str | None = None):
    (tmp_path / "CHANGELOG.md").write_text("## 0.1.0\n- ok\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.1.0"\ndependencies=["PyYAML==6.0.2"]\n'
    )
    (tmp_path / "release.yaml").write_text(
        'version: "0.1.0"\n'
        "attestations:\n"
        "  rollback_tested: {answer: true, by: Eng}\n"
        "  oncall_notified: {answer: false, by: Eng}\n"
        "not_applicable:\n"
        '  monitoring_reviewed: "no runtime infra"\n'
    )

    def runner(args):
        key = " ".join(args)
        return {
            "rev-parse --show-toplevel": f"{root if root is not None else tmp_path}\n",
            "status --porcelain": porcelain,
            "tag --points-at HEAD": tags,
        }.get(key, "")

    return Context(
        repo_path=tmp_path,
        manifest=load(tmp_path / "release.yaml"),
        ci_status="success",
        git=GitAdapter(tmp_path, runner=runner),
    )


def test_specs_expose_the_read_only_tools(tmp_path):
    names = {s["function"]["name"] for s in Toolbox(_context(tmp_path)).specs()}
    assert names == {
        "git_status",
        "git_tags",
        "list_files",
        "read_file",
        "read_manifest",
        "ci_status",
        "run_checks",
    }


def test_read_file_refuses_release_yaml(tmp_path):
    with pytest.raises(ToolError, match="read_manifest"):
        Toolbox(_context(tmp_path)).dispatch("read_file", {"path": "release.yaml"})


def test_read_file_refuses_release_yaml_written_with_dot_slash(tmp_path):
    with pytest.raises(ToolError, match="read_manifest"):
        Toolbox(_context(tmp_path)).dispatch("read_file", {"path": "./release.yaml"})


def test_read_file_allows_a_nested_release_yaml(tmp_path):
    # Only the repo-root manifest is served by read_manifest; a fixture copy
    # deeper in the tree is a normal file.
    nested = tmp_path / "fixtures" / "demo"
    nested.mkdir(parents=True)
    (nested / "release.yaml").write_text('version: "9.9.9"\n')
    box = Toolbox(_context(tmp_path))
    assert box.dispatch("read_file", {"path": "fixtures/demo/release.yaml"}) == 'version: "9.9.9"\n'


def test_read_file_missing_file_error_suggests_list_files(tmp_path):
    with pytest.raises(ToolError, match="list_files"):
        Toolbox(_context(tmp_path)).dispatch("read_file", {"path": "package.json"})


def test_list_files_lists_real_paths_and_skips_junk(tmp_path):
    ctx = _context(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.cpython-311.pyc").write_text("")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("x")
    out = json.loads(Toolbox(ctx).dispatch("list_files", {}))
    assert "CHANGELOG.md" in out["files"]
    assert "release.yaml" in out["files"]
    assert "docs/note.md" in out["files"]
    assert out["truncated"] is False
    assert not any(".git/" in f or "__pycache__/" in f for f in out["files"])


def test_list_files_truncates_at_the_cap(tmp_path):
    ctx = _context(tmp_path)
    for i in range(205):
        (tmp_path / f"f{i:03}.txt").write_text("x")
    out = json.loads(Toolbox(ctx).dispatch("list_files", {}))
    assert len(out["files"]) == 200
    assert out["truncated"] is True


def _write_secrets(tmp_path):
    (tmp_path / ".env").write_text("API_TOKEN=abc\n")
    (tmp_path / ".env.local").write_text("API_TOKEN=abc\n")
    (tmp_path / "secrets.env").write_text("API_TOKEN=abc\n")
    (tmp_path / "server.pem").write_text("-----BEGIN PRIVATE KEY-----\n")
    (tmp_path / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    (tmp_path / "notes.txt").write_text("fine\n")


def test_list_files_never_lists_secrets_or_hidden_files(tmp_path):
    ctx = _context(tmp_path)
    _write_secrets(tmp_path)
    out = json.loads(Toolbox(ctx).dispatch("list_files", {}))
    assert "notes.txt" in out["files"]
    assert "CHANGELOG.md" in out["files"]
    for rel in (".env", ".env.local", "secrets.env", "server.pem", "id_rsa"):
        assert rel not in out["files"]
    assert not any(f.startswith(".github/") for f in out["files"])


def test_read_file_refuses_secrets_and_hidden_files(tmp_path):
    ctx = _context(tmp_path)
    _write_secrets(tmp_path)
    box = Toolbox(ctx)
    for rel in (
        ".env",
        ".env.local",
        "secrets.env",
        "server.pem",
        "id_rsa",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(ToolError, match="secret"):
            box.dispatch("read_file", {"path": rel})


def test_read_file_refuses_secrets_without_confirming_existence(tmp_path):
    # Nothing was created here: the refusal fires before any existence check,
    # so probing for a secrets file cannot even learn whether it exists.
    box = Toolbox(_context(tmp_path))
    with pytest.raises(ToolError, match="secret"):
        box.dispatch("read_file", {"path": ".env"})


def test_read_file_streams_the_cap_and_flags_truncation(tmp_path):
    # A file past the cap returns exactly the cap of bytes, plus a marker the
    # model cannot miss — silent partial evidence was the bug.
    ctx = _context(tmp_path)
    (tmp_path / "big.txt").write_text("y" * (_MAX_FILE_BYTES + 123))
    out = Toolbox(ctx).dispatch("read_file", {"path": "big.txt"})
    body, marker = out[:_MAX_FILE_BYTES], out[_MAX_FILE_BYTES:]
    assert body == "y" * _MAX_FILE_BYTES
    assert "truncated" in marker
    assert "20,000" in marker


def test_read_file_at_exactly_the_cap_is_not_flagged(tmp_path):
    ctx = _context(tmp_path)
    (tmp_path / "edge.txt").write_text("z" * _MAX_FILE_BYTES)
    out = Toolbox(ctx).dispatch("read_file", {"path": "edge.txt"})
    assert out == "z" * _MAX_FILE_BYTES


def test_specs_steer_release_yaml_to_read_manifest(tmp_path):
    # The model used to read release.yaml twice (read_manifest + read_file);
    # the descriptions must keep steering it to read_manifest alone.
    specs = {
        s["function"]["name"]: s["function"]["description"]
        for s in Toolbox(_context(tmp_path)).specs()
    }
    assert "read_manifest" in specs["read_file"]
    assert "read_file" in specs["read_manifest"]


def test_unknown_tool_is_rejected(tmp_path):
    with pytest.raises(ToolError, match="Unknown tool"):
        Toolbox(_context(tmp_path)).dispatch("rm_rf", {})


def test_git_status_reports_clean(tmp_path):
    out = json.loads(Toolbox(_context(tmp_path)).dispatch("git_status", {}))
    assert out == {"clean": True, "porcelain": ""}


def test_git_status_reports_dirty(tmp_path):
    box = Toolbox(_context(tmp_path, porcelain=" M a.txt\n"))
    out = json.loads(box.dispatch("git_status", {}))
    assert out["clean"] is False
    assert "a.txt" in out["porcelain"]


def test_git_status_refuses_to_describe_an_enclosing_repo(tmp_path):
    # If --repo sits inside another repository, its git status would describe
    # the outer repo. The tool must say so instead of reporting that state.
    box = Toolbox(_context(tmp_path, root=str(tmp_path / "outer"), porcelain=" M a.txt\n"))
    with pytest.raises(ToolError, match="not the root of a git repository"):
        box.dispatch("git_status", {})


def test_git_tags_refuses_to_describe_an_enclosing_repo(tmp_path):
    box = Toolbox(_context(tmp_path, root=str(tmp_path / "outer")))
    with pytest.raises(ToolError, match="not the root of a git repository"):
        box.dispatch("git_tags", {})


def test_git_tags_lists_tags(tmp_path):
    box = Toolbox(_context(tmp_path, tags="v0.1.0\nv0.1.1\n"))
    assert json.loads(box.dispatch("git_tags", {})) == {"tags_at_head": ["v0.1.0", "v0.1.1"]}


def test_read_file_returns_repo_content(tmp_path):
    assert Toolbox(_context(tmp_path)).dispatch("read_file", {"path": "CHANGELOG.md"}) == (
        "## 0.1.0\n- ok\n"
    )


def test_read_file_rejects_traversal(tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("nope")
    with pytest.raises(ToolError, match="escapes the repo"):
        Toolbox(_context(tmp_path)).dispatch("read_file", {"path": "../secret.txt"})


def test_read_file_rejects_absolute_path(tmp_path):
    with pytest.raises(ToolError, match="repo-relative"):
        Toolbox(_context(tmp_path)).dispatch("read_file", {"path": "/etc/passwd"})


def test_read_file_rejects_missing_path_argument(tmp_path):
    with pytest.raises(ToolError, match="non-empty 'path'"):
        Toolbox(_context(tmp_path)).dispatch("read_file", {})


def test_read_file_rejects_directory(tmp_path):
    with pytest.raises(ToolError, match="Not a file"):
        Toolbox(_context(tmp_path)).dispatch("read_file", {"path": "."})


def test_read_manifest_serializes_manifest(tmp_path):
    out = json.loads(Toolbox(_context(tmp_path)).dispatch("read_manifest", {}))
    assert out["version"] == "0.1.0"
    assert out["attestations"]["oncall_notified"]["answer"] is False
    assert out["not_applicable"] == {"monitoring_reviewed": "no runtime infra"}


def test_ci_status_returns_injected_value(tmp_path):
    assert json.loads(Toolbox(_context(tmp_path)).dispatch("ci_status", {})) == {
        "ci_status": "success"
    }


def test_run_checks_returns_deterministic_results(tmp_path):
    results = json.loads(Toolbox(_context(tmp_path)).dispatch("run_checks", {}))
    by_id = {r["check_id"]: r for r in results}
    assert by_id["changelog"]["status"] == "PASS"
    assert by_id["release_point"]["status"] == "PASS"
    assert by_id["oncall_notified"]["status"] == "FAIL"
    assert by_id["monitoring_reviewed"]["status"] == "NA"
