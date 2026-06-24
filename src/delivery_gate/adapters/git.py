from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable


def _default_runner(repo_path: Path) -> Callable[[list[str]], str]:
    def run(args: list[str]) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
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
