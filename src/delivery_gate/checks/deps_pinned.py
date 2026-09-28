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
            return Result(
                self.id,
                self.label,
                Status.FAIL,
                self.kind,
                "pyproject.toml not found; cannot verify pinned dependencies.",
            )
        data = tomllib.loads(path.read_text())
        project = data.get("project")
        if not isinstance(project, dict):
            return self._fail("pyproject.toml has no [project] table; cannot verify pins.")
        if "dependencies" in (project.get("dynamic") or []):
            return self._fail("dependencies are declared dynamic; cannot verify pins.")
        deps = project.get("dependencies") or []
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            return self._fail("[project].dependencies is not a list of strings.")
        if not deps:
            return Result(
                self.id, self.label, Status.PASS, self.kind, "No declared dependencies to pin."
            )
        unpinned = [d for d in deps if not _is_pinned(d)]
        if unpinned:
            return Result(
                self.id,
                self.label,
                Status.FAIL,
                self.kind,
                "Unpinned dependencies: " + ", ".join(unpinned),
            )
        return Result(
            self.id, self.label, Status.PASS, self.kind, f"All {len(deps)} dependencies are pinned."
        )

    def _fail(self, message: str) -> Result:
        return Result(self.id, self.label, Status.FAIL, self.kind, message)


def _is_pinned(requirement: str) -> bool:
    # Look at the version part only: an environment marker after ';' can hold
    # '==' (sys_platform == "win32") without pinning anything. '==1.*' is a range.
    spec = requirement.split(";", 1)[0]
    return "==" in spec and "*" not in spec
