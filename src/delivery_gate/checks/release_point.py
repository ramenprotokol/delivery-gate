from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status


class ReleasePointCheck(Check):
    id = "release_point"
    label = "Clean, tagged release point"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        version = context.manifest.version
        git = context.git
        reasons: list[str] = []

        if not git.is_clean():
            reasons.append("working tree has uncommitted changes")

        tag = git.tag_at_head()
        if tag is None:
            reasons.append("no git tag points at HEAD")
        elif tag.lstrip("v") != version.lstrip("v"):
            reasons.append(f"tag '{tag}' does not match manifest version '{version}'")

        if reasons:
            return Result(self.id, self.label, Status.FAIL, self.kind,
                          "; ".join(reasons))
        return Result(self.id, self.label, Status.PASS, self.kind,
                      f"Clean tree on tag '{tag}' matching {version}.")
