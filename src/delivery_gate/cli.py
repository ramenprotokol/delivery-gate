from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from delivery_gate.adapters.git import GitAdapter
from delivery_gate.base import Context
from delivery_gate.manifest import ManifestError, load
from delivery_gate.report import render_json, render_text
from delivery_gate.runner import decide, run_checks


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="delivery-gate")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Run the release gate.")
    check.add_argument("--repo", default=".", help="Path to the repo (default: .)")
    check.add_argument("--ci-status", default=os.environ.get("DELIVERY_GATE_CI_STATUS"),
                       help="CI outcome for the gated commit, e.g. 'success'.")
    check.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo = Path(args.repo)
    try:
        manifest = load(repo / "release.yaml")
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    context = Context(
        repo_path=repo,
        manifest=manifest,
        ci_status=args.ci_status,
        git=GitAdapter(repo),
    )
    results = run_checks(context)
    go = decide(results)
    output = render_json(results, go) if args.json else render_text(results, go)
    print(output)
    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
