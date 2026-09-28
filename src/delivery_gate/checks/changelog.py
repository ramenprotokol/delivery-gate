from __future__ import annotations

import re

from delivery_gate.base import Check, Context, Kind, Result, Status

# A Markdown ATX heading: up to three spaces, then 1-6 '#' and a space.
_HEADING = re.compile(r"^ {0,3}#{1,6}\s")


def _heading_mentions(line: str, version: str) -> bool:
    """True if `line` is a heading naming exactly `version` (optionally v-prefixed)."""
    if not _HEADING.match(line):
        return False
    bare = re.escape(version.lstrip("vV"))
    # Not part of a longer version: 1.0 must not match 1.0.5, 10.1.0 or 1.0-rc1.
    return re.search(rf"(?<![\w.])[vV]?{bare}(?!\w|[.+-]\w)", line) is not None


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
        if any(_heading_mentions(line, version) for line in text.splitlines()):
            return Result(
                self.id, self.label, Status.PASS, self.kind, f"Found a heading for {version}."
            )
        return Result(
            self.id,
            self.label,
            Status.FAIL,
            self.kind,
            f"No CHANGELOG.md heading mentions {version}.",
        )
