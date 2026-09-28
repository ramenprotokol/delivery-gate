from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


class GitError(RuntimeError):
    """Raised when git cannot answer, so checks fail closed instead of guessing."""


def _default_runner(repo_path: Path) -> Callable[[list[str]], str]:
    def run(args: list[str]) -> str:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise GitError(f"could not run git: {exc}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr.strip().splitlines() or [f"exit code {proc.returncode}"])[-1]
            raise GitError(f"git {' '.join(args)} failed: {detail}")
        return proc.stdout

    return run


class GitAdapter:
    def __init__(self, repo_path: Path, runner: Callable[[list[str]], str] | None = None):
        self.repo_path = Path(repo_path)
        self.runner = runner or _default_runner(self.repo_path)

    def is_clean(self) -> bool:
        return self.runner(["status", "--porcelain"]).strip() == ""

    def tag_at_head(self) -> str | None:
        out = self.runner(["tag", "--points-at", "HEAD"]).strip()
        return out.splitlines()[0] if out else None
