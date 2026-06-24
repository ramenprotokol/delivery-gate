from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from delivery_gate.manifest import Manifest
    from delivery_gate.adapters.git import GitAdapter


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "NA"


class Kind(str, Enum):
    AUTO = "AUTO"          # machine-proven
    ATTESTED = "ATTESTED"  # human-claimed


@dataclass(frozen=True)
class Result:
    check_id: str
    label: str
    status: Status
    kind: Kind
    message: str


@dataclass
class Context:
    repo_path: Path
    manifest: "Manifest"
    ci_status: str | None
    git: "GitAdapter"


class Check:
    id: str = "base"
    label: str = "Base check"
    kind: Kind = Kind.AUTO

    def run(self, context: "Context") -> Result:
        raise NotImplementedError
