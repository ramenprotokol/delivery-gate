from __future__ import annotations

import tomllib

from delivery_gate.base import Check, Context, Kind, Result, Status


class DepsPinnedCheck(Check):
    id = "deps_pinned"
    label = "Dependencies pinned to exact versions"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        path = context.repo_path / "pyproject.toml"
        if not path.exists():
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "pyproject.toml not found; cannot verify pinned dependencies.")
        data = tomllib.loads(path.read_text())
        deps = (data.get("project") or {}).get("dependencies") or []
        if not deps:
            return Result(self.id, self.label, Status.PASS, self.kind,
                          "No declared dependencies to pin.")
        unpinned = [d for d in deps if "==" not in d]
        if unpinned:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "Unpinned dependencies: " + ", ".join(unpinned))
        return Result(self.id, self.label, Status.PASS, self.kind,
                      f"All {len(deps)} dependencies are pinned.")
