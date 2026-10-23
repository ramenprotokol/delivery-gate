from __future__ import annotations

import json
import os
from pathlib import Path

from delivery_gate.adapters.git import GitError
from delivery_gate.base import Context, Result
from delivery_gate.runner import run_checks

# Investigate mode is read-only and confined to the repo. These caps keep a
# misbehaving model from pulling an entire repository (or a huge file) into the
# conversation.
_MAX_FILE_BYTES = 20_000
_MAX_LISTED_FILES = 200
_SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}

# Anything hidden or key-shaped is off-limits: an investigation has no business
# reading secrets, and the conversation (or --trace) would echo them straight
# back out. One predicate serves both list_files (never listed) and read_file
# (always refused, without confirming the file exists).
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_SECRET_NAMES = {"secrets.env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}


def _skipped_dir(name: str) -> bool:
    return name.startswith(".") or name in _SKIP_DIRS or name.endswith(".egg-info")


def _is_secret(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    name = parts[-1] if parts else ""
    return (
        any(part.startswith(".") for part in parts)
        or name in _SECRET_NAMES
        or name.endswith(_SECRET_SUFFIXES)
    )


class ToolError(RuntimeError):
    """Raised for a bad tool call; the agent loop reports it back to the model."""


def schema(properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


class Toolbox:
    """The read-only tools the investigating model may call."""

    def __init__(self, context: Context):
        self.context = context

    def specs(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "git_status",
                    "description": "Show the git working-tree status. Reports whether the tree "
                    "is clean and the raw porcelain output.",
                    "parameters": schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "git_tags",
                    "description": "List the git tags that point at HEAD.",
                    "parameters": schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List the files that actually exist in the repository, as "
                    "repo-relative paths. Use this instead of guessing file names.",
                    "parameters": schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a text file inside the repository, given a repo-relative "
                    "path. Paths outside the repo are rejected, and hidden or "
                    "secret-looking files (dotfiles, .env-style files, keys, certificates) "
                    "are refused. Files longer than 20,000 bytes are truncated and the "
                    "result says so. For release.yaml use read_manifest instead.",
                    "parameters": schema(
                        {"path": {"type": "string", "description": "Repo-relative file path."}},
                        ["path"],
                    ),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_manifest",
                    "description": "Read the parsed release.yaml manifest: version, attestations "
                    "and not_applicable entries. This covers all of release.yaml; there is no "
                    "need to also read_file it.",
                    "parameters": schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "ci_status",
                    "description": "Return the CI status string that was passed to the gate.",
                    "parameters": schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_checks",
                    "description": "Run the deterministic release checks and return each result "
                    "(status, kind, message). This is the authoritative gate result.",
                    "parameters": schema(),
                },
            },
        ]

    def dispatch(self, name: str, arguments: dict) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ToolError(f"Unknown tool: {name}")
        return handler(arguments)

    def _not_repo_root(self, git) -> str:
        # git with cwd inside a nested path reports the *enclosing* repo; that
        # status and those tags would describe the wrong repository.
        root = git.repo_root()
        return (
            f"--repo is not the root of a git repository; it sits inside '{root}', "
            f"so its git state (status, tags) belongs to that outer repo. Point --repo "
            f"at a real repository root, or make this path its own repository."
        )

    def _tool_git_status(self, arguments: dict) -> str:
        git = self.context.git
        try:
            if not git.is_repo_root():
                raise ToolError(self._not_repo_root(git))
            porcelain = git.status_porcelain()
        except GitError as exc:
            raise ToolError(f"could not read git status: {exc}") from exc
        return json.dumps({"clean": porcelain.strip() == "", "porcelain": porcelain})

    def _tool_git_tags(self, arguments: dict) -> str:
        try:
            if not self.context.git.is_repo_root():
                raise ToolError(self._not_repo_root(self.context.git))
            tags = self.context.git.tags_at_head()
        except GitError as exc:
            raise ToolError(f"could not read git tags: {exc}") from exc
        return json.dumps({"tags_at_head": tags})

    def _tool_list_files(self, arguments: dict) -> str:
        root = self.context.repo_path.resolve()
        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not _skipped_dir(d))
            for name in sorted(filenames):
                rel = (Path(dirpath) / name).relative_to(root).as_posix()
                if _is_secret(rel):
                    continue
                files.append(rel)
                if len(files) >= _MAX_LISTED_FILES:
                    return json.dumps({"files": files, "truncated": True})
        return json.dumps({"files": files, "truncated": False})

    def _tool_read_file(self, arguments: dict) -> str:
        path = arguments.get("path")
        if not isinstance(path, str) or not path:
            raise ToolError("read_file requires a non-empty 'path'.")
        root, target = self._resolve(path)
        if _is_secret(target.relative_to(root).as_posix()):
            # Refused before the existence check: probing for a secrets file
            # must not even learn whether it is there.
            raise ToolError(
                "read_file refuses hidden and secret-looking files (dotfiles, "
                ".env-style files, keys and certificates)."
            )
        if target == root / "release.yaml":
            # The manifest is already served parsed; a second raw read just
            # duplicates the evidence, so the tool refuses and says where to go.
            raise ToolError("read_file refuses release.yaml; use read_manifest instead.")
        if not target.is_file():
            raise ToolError(f"Not a file in the repo: {path}. Call list_files to see what exists.")
        # Stream at most the cap: read_bytes() would pull a huge file (a wheel,
        # a SQL dump) entirely into memory before the slice threw most of it
        # away. Read one byte past the cap to learn whether the file continues.
        with target.open("rb") as handle:
            raw = handle.read(_MAX_FILE_BYTES + 1)
        truncated = len(raw) > _MAX_FILE_BYTES
        text = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        if truncated:
            text += (
                f"\n\n[read_file: truncated — only the first {_MAX_FILE_BYTES:,} bytes of a "
                "longer file are shown; do not treat this as the whole file]"
            )
        return text

    def _tool_read_manifest(self, arguments: dict) -> str:
        manifest = self.context.manifest
        return json.dumps(
            {
                "version": manifest.version,
                "attestations": {
                    key: {"answer": att.answer, "by": att.by, "evidence": att.evidence}
                    for key, att in manifest.attestations.items()
                },
                "not_applicable": manifest.not_applicable,
            }
        )

    def _tool_ci_status(self, arguments: dict) -> str:
        return json.dumps({"ci_status": self.context.ci_status})

    def _tool_run_checks(self, arguments: dict) -> str:
        results: list[Result] = run_checks(self.context)
        return json.dumps(
            [
                {
                    "check_id": r.check_id,
                    "label": r.label,
                    "status": r.status.value,
                    "kind": r.kind.value,
                    "message": r.message,
                }
                for r in results
            ]
        )

    def _resolve(self, path: str) -> tuple[Path, Path]:
        candidate = Path(path)
        if candidate.is_absolute():
            raise ToolError("read_file needs a repo-relative path, not an absolute one.")
        root = self.context.repo_path.resolve()
        target = (root / candidate).resolve()
        if target != root and not target.is_relative_to(root):
            raise ToolError(f"Path escapes the repo: {path}")
        return root, target
