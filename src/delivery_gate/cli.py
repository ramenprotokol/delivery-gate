from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from delivery_gate.adapters.git import GitAdapter
from delivery_gate.base import Context
from delivery_gate.cases import CasesError, load_cases, load_repos, run_cases
from delivery_gate.investigate import DEFAULT_MAX_STEPS, investigate
from delivery_gate.investigate import render_json as render_investigation_json
from delivery_gate.investigate import render_text as render_investigation_text
from delivery_gate.llm import LlmClient, LlmError
from delivery_gate.manifest import ManifestError, load
from delivery_gate.report import render_json, render_text
from delivery_gate.runner import decide, run_checks


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Path to the repo (default: .)")
    parser.add_argument(
        "--ci-status",
        default=os.environ.get("DELIVERY_GATE_CI_STATUS"),
        help="CI outcome for the gated commit, e.g. 'success'.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="delivery-gate")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Run the release gate.")
    _add_common_arguments(check)

    investigate_parser = sub.add_parser(
        "investigate",
        help="Ask a model to work out why a release is blocked and what to fix.",
    )
    _add_common_arguments(investigate_parser)
    investigate_parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=(
            "Maximum model round-trips; one round-trip may issue several tool calls "
            f"(default: {DEFAULT_MAX_STEPS})."
        ),
    )
    investigate_parser.add_argument(
        "--model", default=None, help="Model to use (default: $DELIVERY_GATE_LLM_MODEL)."
    )
    investigate_parser.add_argument(
        "--brief-model",
        default=None,
        help="Model that writes the final brief (default: the same model runs everything).",
    )
    investigate_parser.add_argument(
        "--trace",
        action="store_true",
        help="Print each tool call and its result to stderr.",
    )

    cases_parser = sub.add_parser(
        "cases",
        help="Run fixed test cases through investigate against made-up repos and write a log.",
    )
    cases_parser.add_argument("--cases", required=True, help="Cases file (JSON lines).")
    cases_parser.add_argument("--repos", required=True, help="Made-up repos file (JSON).")
    cases_parser.add_argument("--log", required=True, help="Where to write the run log.")
    cases_parser.add_argument(
        "--model", default=None, help="Model to use (default: $DELIVERY_GATE_LLM_MODEL)."
    )
    cases_parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=f"Maximum model round-trips per case (default: {DEFAULT_MAX_STEPS}).",
    )
    return parser


def _run_cases(args: argparse.Namespace) -> int:
    try:
        repos = load_repos(Path(args.repos))
        cases = load_cases(Path(args.cases), repos)
        client = LlmClient.from_env(model=args.model)
        run_cases(
            cases,
            repos,
            client,
            Path(args.log),
            api_key=client.api_key,
            max_steps=args.max_steps,
        )
    except (CasesError, LlmError, OSError) as exc:
        print(f"cases: {exc}", file=sys.stderr)
        return 2
    return 0


def _run_check(args: argparse.Namespace, context: Context) -> int:
    results = run_checks(context)
    go = decide(results)
    output = render_json(results, go) if args.json else render_text(results, go)
    print(output)
    return 0 if go else 1


def _run_investigate(args: argparse.Namespace, context: Context) -> int:
    trace = (lambda message: print(f"[trace] {message}", file=sys.stderr)) if args.trace else None
    try:
        client = LlmClient.from_env(model=args.model)
        brief = investigate(
            context,
            client,
            max_steps=args.max_steps,
            trace=trace,
            brief_model=args.brief_model,
        )
    except LlmError as exc:
        print(f"investigate: {exc}", file=sys.stderr)
        return 2
    output = render_investigation_json(brief) if args.json else render_investigation_text(brief)
    print(output)
    return 0 if brief.decision == "GO" else 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "cases":
        return _run_cases(args)
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
    if args.command == "investigate":
        return _run_investigate(args, context)
    return _run_check(args, context)


if __name__ == "__main__":
    raise SystemExit(main())
