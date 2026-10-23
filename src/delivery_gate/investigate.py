from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace

from delivery_gate.base import Context, Result, Status
from delivery_gate.llm import LlmClient, LlmError
from delivery_gate.runner import decide, run_checks
from delivery_gate.tools import Toolbox, ToolError, schema

DEFAULT_MAX_STEPS = 12

_SYSTEM_PROMPT = """\
You are the release-gate investigator for a repository. A release is blocked or \
allowed by a fixed set of deterministic checks; your job is to work out *why*, \
grounded in evidence, and tell the operator what to fix.

Rules:
- Use the tools to gather evidence. Start by calling run_checks: it returns the \
authoritative result of every check. Never guess a result you can look up.
- Never guess file names: call list_files to see which files exist. The manifest \
is served by read_manifest; read_file refuses release.yaml.
- Investigate only checks that FAIL (or that you have reason to doubt). Read the \
relevant files, the manifest, git state and the CI status.
- If run_checks or a git tool reports that the repository is not the root of a \
git repository, say exactly that: git state belongs to the enclosing repository \
and cannot verify this release point. The fix is to point --repo at a real \
repository root or make the path its own repository — never to commit or tag \
the enclosing repository, and never to describe its state as this repo's.
- Quote concrete evidence (file contents, tag names, messages) in your findings.
- You cannot change the decision: it is fixed by run_checks. Do not claim a \
blocked release is GO.
- When done, call the `finish` tool exactly once with a short summary and one \
finding per problem, each with a concrete fix.
"""

_FINISH_SPEC = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": "End the investigation with a summary and findings.",
        "parameters": schema(
            {
                "summary": {
                    "type": "string",
                    "description": "Two or three sentences on why the release is blocked or not.",
                },
                "findings": {
                    "type": "array",
                    "description": "One entry per problem, grounded in evidence.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "check_id": {"type": "string"},
                            "explanation": {"type": "string"},
                            "fix": {"type": "string"},
                        },
                        "required": ["check_id", "explanation"],
                    },
                },
            },
            ["summary"],
        ),
    },
}


@dataclass(frozen=True)
class BriefItem:
    check_id: str
    label: str
    status: str
    kind: str
    explanation: str
    fix: str | None


@dataclass(frozen=True)
class Brief:
    decision: str
    summary: str
    blocking: list[BriefItem]
    notes: list[BriefItem]
    steps: int


def _system_message(context: Context) -> str:
    return (
        f"{_SYSTEM_PROMPT}\n"
        f"Repository: {context.repo_path}\n"
        f"Manifest version: {context.manifest.version}\n"
        f"CI status passed in: {context.ci_status!r}\n"
    )


def _short(value: object, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def investigate(
    context: Context,
    client: LlmClient,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    trace: Callable[[str], None] | None = None,
    brief_model: str | None = None,
) -> Brief:
    toolbox = Toolbox(context)
    tools = [*toolbox.specs(), _FINISH_SPEC]
    messages: list[dict] = [
        {"role": "system", "content": _system_message(context)},
        {
            "role": "user",
            "content": "Investigate why this release is blocked (or confirm it is ready) "
            "and finish with a brief.",
        },
    ]

    finish_args: dict | None = None
    last_content = ""
    transcript: list[str] = []
    steps = 0
    stopped = False
    error_note = None
    for _ in range(max_steps):
        steps += 1
        try:
            reply = client.chat(messages, tools=tools)
        except LlmError as exc:
            # The decision needs no model; a dead or flaky model API must not
            # cost the operator the anchored result they came for.
            error_note = (
                f"The investigation was cut off at model step {steps} "
                f"({_short(str(exc), 200)}); the decision below comes from the "
                "deterministic checks alone. Re-run investigate when the model API "
                "is reachable for the full brief."
            )
            if trace:
                trace(
                    f"{client.model}: model API error at step {steps} ({_short(str(exc))}); "
                    "falling back to the anchored decision"
                )
            break
        last_content = reply.content or last_content
        if not reply.tool_calls:
            stopped = True
            break

        messages.append(
            {
                "role": "assistant",
                "content": reply.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                    for call in reply.tool_calls
                ],
            }
        )

        for call in reply.tool_calls:
            if call.name == "finish":
                finish_args = call.arguments
                if trace:
                    trace(f"{client.model}: finish({_short(call.arguments)})")
                continue
            try:
                output = toolbox.dispatch(call.name, call.arguments)
            except ToolError as exc:
                output = json.dumps({"error": str(exc)})
            transcript.append(f"{call.name}({_short(call.arguments)}) -> {_short(output, 400)}")
            if trace:
                trace(f"{client.model}: {call.name}({_short(call.arguments)}) -> {_short(output)}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

        if finish_args is not None:
            stopped = True
            break

    # A step is one model round-trip, which may issue several tool calls; if the
    # budget ran out without `finish`, the loop's last text is a half-finished
    # thought, not a summary — say the cap was hit instead of hiding it.
    cap_note = None
    if not stopped and error_note is None:
        cap_note = (
            f"The investigation hit its step cap ({max_steps} model steps) without a final "
            f"answer; re-run with a larger --max-steps."
        )
        if trace:
            trace(f"{client.model}: step cap of {max_steps} reached without finish")

    fallback = last_content
    if error_note:
        tail = f" Last model output before the cutoff: {_short(last_content, 300)}"
        fallback = error_note + (tail if last_content.strip() else "")
    elif cap_note:
        tail = f" Last model output before the cap: {_short(last_content, 300)}"
        fallback = cap_note + (tail if last_content.strip() else "")

    results = run_checks(context)
    brief = build_brief(results, finish_args, summary_fallback=fallback, steps=steps)
    # After a cutoff the brief model would hit the same dead model API; the note
    # already explains everything, so skip it.
    if brief_model is not None and error_note is None:
        steps += 1
        summary = _compose_brief_summary(
            client,
            brief_model,
            brief=brief,
            results=results,
            transcript=transcript,
            trace=trace,
        )
        if summary is not None:
            if cap_note:
                summary = f"{summary} {cap_note}"
            brief = replace(brief, summary=summary, steps=steps)
        else:
            brief = replace(brief, steps=steps)
    return brief


_BRIEF_SYSTEM = (
    "You write the final summary of a release-gate investigation. The GO/NO-GO decision is "
    "already fixed by deterministic checks and shown to you; you cannot change it. Using only "
    "the decision, check results, evidence and draft summary below, write 3-6 sentences of "
    "plain prose saying why the release is or is not blocked and what to fix first. Do not "
    "invent facts, mention tool names or JSON, or contradict the decision."
)


def _compose_brief_summary(
    client: LlmClient,
    model: str,
    *,
    brief: Brief,
    results: list[Result],
    transcript: list[str],
    trace: Callable[[str], None] | None,
) -> str | None:
    payload = json.dumps(
        {
            "decision": brief.decision,
            "checks": [
                {
                    "check_id": r.check_id,
                    "label": r.label,
                    "status": r.status.value,
                    "kind": r.kind.value,
                    "message": r.message,
                }
                for r in results
            ],
            "draft_summary": brief.summary,
            "evidence": transcript[-24:],
        }
    )
    messages = [
        {"role": "system", "content": _BRIEF_SYSTEM},
        {"role": "user", "content": payload},
    ]
    try:
        reply = client.chat(messages, model=model)
    except LlmError as exc:
        if trace:
            trace(f"{model}: brief failed ({_short(str(exc))}); keeping the loop summary")
        return None
    summary = (reply.content or "").strip()
    if not summary:
        if trace:
            trace(f"{model}: brief returned no text; keeping the loop summary")
        return None
    if trace:
        trace(f"{model}: brief -> {_short(summary)}")
    return summary


def build_brief(
    results: list[Result], finish_args: dict | None, *, summary_fallback: str = "", steps: int = 0
) -> Brief:
    go = decide(results)
    finish_args = finish_args or {}
    summary = finish_args.get("summary") if isinstance(finish_args.get("summary"), str) else ""
    summary = summary.strip() or summary_fallback.strip() or "No summary provided."

    findings = _normalize_findings(finish_args.get("findings"))
    by_id = {f["check_id"]: f for f in findings}

    blocking: list[BriefItem] = []
    for result in results:
        if result.status is not Status.FAIL:
            continue
        finding = by_id.pop(result.check_id, None)
        blocking.append(
            BriefItem(
                check_id=result.check_id,
                label=result.label,
                status=result.status.value,
                kind=result.kind.value,
                explanation=(finding or {}).get("explanation") or result.message,
                fix=(finding or {}).get("fix"),
            )
        )

    # Leftover findings are notes. When they name a real check, carry that
    # check's label, kind and status so notes look like blocking items; for
    # check_ids outside the gate there is no ground truth, so keep NOTE.
    by_check_id = {r.check_id: r for r in results}
    notes: list[BriefItem] = []
    for f in findings:
        if f["check_id"] not in by_id:
            continue
        result = by_check_id.get(f["check_id"])
        notes.append(
            BriefItem(
                check_id=f["check_id"],
                label=result.label if result else f["check_id"],
                status=result.status.value if result else "NOTE",
                kind=result.kind.value if result else "",
                explanation=f.get("explanation") or "",
                fix=f.get("fix"),
            )
        )

    return Brief(
        decision="GO" if go else "NO-GO",
        summary=summary,
        blocking=blocking,
        notes=notes,
        steps=steps,
    )


def _normalize_findings(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    findings: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        check_id = item.get("check_id")
        if not isinstance(check_id, str) or not check_id:
            continue
        findings.append(
            {
                "check_id": check_id,
                "explanation": item.get("explanation")
                if isinstance(item.get("explanation"), str)
                else "",
                "fix": item.get("fix") if isinstance(item.get("fix"), str) else None,
            }
        )
    return findings


def render_text(brief: Brief) -> str:
    lines = ["delivery-gate investigation", "=" * 40, f"Decision: {brief.decision}", ""]
    lines.append(brief.summary)
    if brief.blocking:
        lines.append("")
        lines.append("Blocking items:")
        for item in brief.blocking:
            lines.append(f"  - [{item.check_id}] {item.label}")
            lines.append(f"      {item.explanation}")
            if item.fix:
                lines.append(f"      fix: {item.fix}")
    if brief.notes:
        lines.append("")
        lines.append("Other notes:")
        for item in brief.notes:
            lines.append(f"  - [{item.check_id}] {item.explanation}")
            if item.fix:
                lines.append(f"      fix: {item.fix}")
    return "\n".join(lines)


def render_json(brief: Brief) -> str:
    return json.dumps(
        {
            "decision": brief.decision,
            "summary": brief.summary,
            "steps": brief.steps,
            "blocking": [item.__dict__ for item in brief.blocking],
            "notes": [item.__dict__ for item in brief.notes],
        },
        indent=2,
    )
