from __future__ import annotations

from delivery_gate.base import Check, Context, Kind, Result, Status


class ChangelogCheck(Check):
    id = "changelog"
    label = "CHANGELOG updated for this version"
    kind = Kind.AUTO

    def run(self, context: Context) -> Result:
        path = context.repo_path / "CHANGELOG.md"
        version = context.manifest.version
        if not path.exists():
            return Result(
                self.id, self.label, Status.FAIL, self.kind, "CHANGELOG.md not found at repo root."
            )
        text = path.read_text()
        if version in text:
            return Result(
                self.id, self.label, Status.PASS, self.kind, f"Found an entry for {version}."
            )
        return Result(
            self.id,
            self.label,
            Status.FAIL,
            self.kind,
            f"No CHANGELOG.md entry mentions {version}.",
        )
