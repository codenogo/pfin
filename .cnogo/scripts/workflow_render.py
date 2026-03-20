#!/usr/bin/env python3
"""
Render markdown artifacts from JSON contracts to reduce drift.

Supported:
- ideas/<initiative>/SHAPE.json -> SHAPE.md
- ideas/<initiative>/BRAINSTORM.json -> BRAINSTORM.md (legacy)
- features/<feature>/FEATURE.json -> FEATURE.md
- features/<feature>/CONTEXT.json -> CONTEXT.md
- features/<feature>/<NN>-PLAN.json -> <NN>-PLAN.md (regenerates tasks section)
- features/<feature>/<NN>-SUMMARY.json -> <NN>-SUMMARY.md (regenerates tables)
- work/research/<slug>/RESEARCH.json -> RESEARCH.md

This is intentionally simple and deterministic.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from workflow_utils import load_json
except ModuleNotFoundError:
    from .workflow_utils import load_json  # type: ignore


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def render_shape(shape: dict[str, Any]) -> str:
    initiative = str(shape.get("initiative") or shape.get("topic") or "[Initiative]").strip()
    problem = str(shape.get("problem") or "[Problem statement]").strip()
    constraints = shape.get("constraints", [])
    global_decisions = shape.get("globalDecisions", [])
    decision_log = shape.get("decisionLog", [])
    shape_threads = shape.get("shapeThreads", [])
    research_refs = shape.get("researchRefs", [])
    open_questions = shape.get("openQuestions", [])
    candidate_features = shape.get("candidateFeatures", [])
    next_shape_moves = shape.get("nextShapeMoves", [])
    recommended_sequence = shape.get("recommendedSequence", [])

    lines: list[str] = []
    lines.append(f"# Shape: {initiative}")
    lines.append("")
    lines.append("## Problem")
    lines.append(problem or "[Problem statement]")
    lines.append("")
    lines.append("## Constraints")
    if isinstance(constraints, list) and constraints:
        for item in constraints:
            lines.append(f"- {item}")
    else:
        lines.append("- [Constraint]")
    lines.append("")
    lines.append("## Stable Decisions")
    if (isinstance(global_decisions, list) and global_decisions) or (isinstance(decision_log, list) and decision_log):
        for item in global_decisions:
            lines.append(f"- {item}")
        if isinstance(decision_log, list):
            for entry in decision_log:
                if not isinstance(entry, dict):
                    continue
                title = str(entry.get("title") or "[Decision]").strip()
                decision = str(entry.get("decision") or "[Decision detail]").strip()
                rationale = str(entry.get("rationale") or "").strip()
                line = f"- {title}: {decision}"
                if rationale:
                    line = f"{line} ({rationale})"
                lines.append(line)
    else:
        lines.append("- [Stable cross-feature decision]")
    lines.append("")
    lines.append("## Active Shape Threads")
    if isinstance(shape_threads, list) and shape_threads:
        for entry in shape_threads:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "[Thread]").strip()
            summary = str(entry.get("summary") or "[Thread summary]").strip()
            status = str(entry.get("status") or "[status]").strip()
            related_features = entry.get("relatedFeatures", [])
            lines.append(f"### {title}")
            lines.append(f"- Status: `{status}`")
            lines.append(f"- Summary: {summary}")
            if isinstance(related_features, list) and related_features:
                lines.append("- Related Features:")
                for feature in related_features:
                    lines.append(f"  - `{feature}`")
            lines.append("")
    else:
        lines.append("- [No active shaping thread recorded]")
        lines.append("")
    lines.append("## Feature Queue")
    lines.append("| Feature | Status | User Outcome |")
    lines.append("|---------|--------|--------------|")
    discuss_ready: list[tuple[str, str]] = []
    if isinstance(candidate_features, list) and candidate_features:
        for feature in candidate_features:
            if not isinstance(feature, dict):
                continue
            slug = str(feature.get("slug", "")).strip()
            display_name = str(feature.get("displayName") or slug or "[Feature]").strip()
            if feature.get("status") == "discuss-ready" and slug:
                discuss_ready.append((slug, display_name))
            lines.append(
                "| `{}` | `{}` | {} |".format(
                    slug,
                    feature.get("status", ""),
                    feature.get("userOutcome", ""),
                )
            )
    else:
        lines.append("| `feature-slug` | `draft` | [User outcome] |")
    lines.append("")
    lines.append("## Feature Handoffs")
    if isinstance(candidate_features, list) and candidate_features:
        for feature in candidate_features:
            if not isinstance(feature, dict):
                continue
            slug = str(feature.get("slug") or "feature-slug").strip()
            display_name = str(feature.get("displayName") or slug or "[Feature]").strip()
            scope_summary = str(feature.get("scopeSummary") or "[Scope summary]").strip()
            readiness_reason = str(feature.get("readinessReason") or "[Why it is in this state]").strip()
            handoff_summary = str(feature.get("handoffSummary") or "[What discuss should refine next]").strip()
            dependencies = feature.get("dependencies", [])
            risks = feature.get("risks", [])

            lines.append(f"### {display_name}")
            lines.append(f"- Slug: `{slug}`")
            lines.append(f"- Scope: {scope_summary}")
            lines.append(f"- Readiness: {readiness_reason}")
            lines.append(f"- Handoff: {handoff_summary}")
            lines.append("- Dependencies:")
            if isinstance(dependencies, list) and dependencies:
                for item in dependencies:
                    lines.append(f"  - {item}")
            else:
                lines.append("  - [None]")
            lines.append("- Risks:")
            if isinstance(risks, list) and risks:
                for item in risks:
                    lines.append(f"  - {item}")
            else:
                lines.append("  - [None identified]")
            lines.append("")
    else:
        lines.append("### [Feature]")
        lines.append("- Slug: `feature-slug`")
        lines.append("- Scope: [Scope summary]")
        lines.append("- Readiness: [Why it is in this state]")
        lines.append("- Handoff: [What discuss should refine next]")
        lines.append("- Dependencies:")
        lines.append("  - [None]")
        lines.append("- Risks:")
        lines.append("  - [None identified]")
        lines.append("")
    lines.append("## Suggested Next Shape Moves")
    if isinstance(next_shape_moves, list) and next_shape_moves:
        for item in next_shape_moves:
            lines.append(f"- {item}")
    else:
        lines.append("- [Continue shaping by splitting, comparing, resequencing, promoting, parking, or reopening work]")
    lines.append("")
    lines.append("## Optional Discuss Exits")
    if discuss_ready:
        for slug, display_name in discuss_ready:
            lines.append(f"- `/discuss {slug}` - {display_name}")
    else:
        lines.append("- [No discuss-ready feature yet]")
    lines.append("")
    lines.append("## Recommended Sequence")
    if isinstance(recommended_sequence, list) and recommended_sequence:
        for slug in recommended_sequence:
            lines.append(f"- `{slug}`")
    else:
        lines.append("- `[feature-slug]`")
    lines.append("")
    lines.append("## Research")
    if isinstance(research_refs, list) and research_refs:
        for item in research_refs:
            lines.append(f"- {item}")
    else:
        lines.append("- [Optional research reference]")
    lines.append("")
    lines.append("## Open Questions")
    if isinstance(open_questions, list) and open_questions:
        for item in open_questions:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("- [ ] [Open question]")
    lines.append("")
    return "\n".join(lines)


def render_brainstorm(brainstorm: dict[str, Any]) -> str:
    topic = str(brainstorm.get("topic") or "[Idea]").strip()
    constraints = brainstorm.get("constraints", [])
    questions = brainstorm.get("questionsAsked", [])
    candidates = brainstorm.get("candidates", [])
    recommendation = brainstorm.get("recommendation", {})

    lines: list[str] = []
    lines.append(f"# Brainstorm: {topic}")
    lines.append("")
    lines.append("## Questions Asked")
    if isinstance(questions, list) and questions:
        for item in questions:
            lines.append(f"- {item}")
    else:
        lines.append("- [Question]")
    lines.append("")
    lines.append("## Constraints")
    if isinstance(constraints, list) and constraints:
        for item in constraints:
            lines.append(f"- {item}")
    else:
        lines.append("- [Constraint]")
    lines.append("")
    lines.append("## Candidate Directions")
    if isinstance(candidates, list) and candidates:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            lines.append(f"### {candidate.get('name', '[Option]')}")
            lines.append(str(candidate.get("summary", "[Summary]")))
            lines.append("")
    else:
        lines.append("### [Option]")
        lines.append("[Summary]")
        lines.append("")
    lines.append("## Recommendation")
    if isinstance(recommendation, dict):
        lines.append(f"- Primary: {recommendation.get('primary', '[Option]')}")
        lines.append(f"- Backup: {recommendation.get('backup', '[Option]')}")
    else:
        lines.append("- Primary: [Option]")
    lines.append("")
    return "\n".join(lines)


def render_feature_stub(feature: dict[str, Any]) -> str:
    display_name = str(feature.get("displayName") or feature.get("feature") or "[Feature]").strip()
    user_outcome = str(feature.get("userOutcome") or "[User outcome]").strip()
    scope_summary = str(feature.get("scopeSummary") or "[Scope summary]").strip()
    dependencies = feature.get("dependencies", [])
    risks = feature.get("risks", [])
    status = str(feature.get("status") or "draft").strip()
    readiness_reason = str(feature.get("readinessReason") or "[Why it is in this state]").strip()
    handoff_summary = str(feature.get("handoffSummary") or "[What discuss should refine next]").strip()
    parent_shape = feature.get("parentShape", {})

    lines: list[str] = []
    lines.append(f"# Feature: {display_name}")
    lines.append("")
    lines.append("## User Outcome")
    lines.append(user_outcome)
    lines.append("")
    lines.append("## Scope Summary")
    lines.append(scope_summary)
    lines.append("")
    lines.append("## Status")
    lines.append(f"`{status}`")
    lines.append("")
    lines.append("## Dependencies")
    if isinstance(dependencies, list) and dependencies:
        for item in dependencies:
            lines.append(f"- {item}")
    else:
        lines.append("- [Dependency or none]")
    lines.append("")
    lines.append("## Risks")
    if isinstance(risks, list) and risks:
        for item in risks:
            lines.append(f"- {item}")
    else:
        lines.append("- [Risk]")
    lines.append("")
    lines.append("## Readiness Reason")
    lines.append(readiness_reason)
    lines.append("")
    lines.append("## Handoff Summary")
    lines.append(handoff_summary)
    lines.append("")
    lines.append("## Parent Shape")
    if isinstance(parent_shape, dict) and parent_shape:
        lines.append(f"- Path: `{parent_shape.get('path', '[path]')}`")
        lines.append(f"- Timestamp: `{parent_shape.get('timestamp', '[timestamp]')}`")
    else:
        lines.append("- [No parent shape linkage recorded]")
    lines.append("")
    return "\n".join(lines)


def render_context(context: dict[str, Any]) -> str:
    display_name = str(context.get("displayName") or context.get("feature") or "[Feature]").strip()
    decisions = context.get("decisions", [])
    constraints = context.get("constraints", [])
    open_questions = context.get("openQuestions", [])
    related_code = context.get("relatedCode", [])
    research = context.get("research", [])
    parent_shape = context.get("parentShape", {})
    feature_stub = context.get("featureStub", {})
    shape_feedback = context.get("shapeFeedback", [])

    lines: list[str] = []
    lines.append(f"# Context: {display_name}")
    lines.append("")
    lines.append("## Decisions")
    if isinstance(decisions, list) and decisions:
        for entry in decisions:
            if isinstance(entry, dict):
                area = str(entry.get("area") or "[Area]").strip()
                decision = str(entry.get("decision") or "[Decision]").strip()
                rationale = str(entry.get("rationale") or "").strip()
                lines.append(f"- {area}: {decision}")
                if rationale:
                    lines.append(f"  - Rationale: {rationale}")
            else:
                lines.append(f"- {entry}")
    else:
        lines.append("- [Feature-local decision]")
    lines.append("")
    lines.append("## Constraints")
    if isinstance(constraints, list) and constraints:
        for item in constraints:
            lines.append(f"- {item}")
    else:
        lines.append("- [Constraint]")
    lines.append("")
    lines.append("## Related Code")
    if isinstance(related_code, list) and related_code:
        for item in related_code:
            lines.append(f"- `{item}`")
    else:
        lines.append("- `path/to/file`")
    lines.append("")
    lines.append("## Research")
    if isinstance(research, list) and research:
        for item in research:
            lines.append(f"- {item}")
    else:
        lines.append("- [Optional research reference]")
    lines.append("")
    lines.append("## Parent Links")
    if isinstance(parent_shape, dict) and parent_shape:
        lines.append(f"- Shape: `{parent_shape.get('path', '[path]')}`")
    if isinstance(feature_stub, dict) and feature_stub:
        lines.append(f"- Feature Stub: `{feature_stub.get('path', '[path]')}`")
    if not ((isinstance(parent_shape, dict) and parent_shape) or (isinstance(feature_stub, dict) and feature_stub)):
        lines.append("- [No parent links recorded]")
    lines.append("")
    lines.append("## Open Questions")
    if isinstance(open_questions, list) and open_questions:
        for item in open_questions:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("- [ ] [Open question]")
    lines.append("")
    lines.append("## Suggested Shape Feedback")
    if isinstance(shape_feedback, list) and shape_feedback:
        for entry in shape_feedback:
            if isinstance(entry, dict):
                summary = str(entry.get("summary") or "[Suggested update]").strip()
                suggested_action = str(entry.get("suggestedAction") or "").strip()
                lines.append(f"- {summary}")
                if suggested_action:
                    lines.append(f"  - Suggested Action: {suggested_action}")
            else:
                lines.append(f"- {entry}")
    else:
        lines.append("- [No shape feedback recorded]")
    lines.append("")
    return "\n".join(lines)


def render_research(research: dict[str, Any]) -> str:
    topic = str(research.get("topic") or "[Topic]").strip()
    mode = str(research.get("mode") or "[mode]").strip()
    summary = research.get("summary", [])
    sources = research.get("sources", [])
    recommendation = research.get("recommendation")

    lines: list[str] = []
    lines.append(f"# Research: {topic}")
    lines.append("")
    lines.append("## Mode")
    lines.append(f"`{mode}`")
    lines.append("")
    lines.append("## Summary")
    if isinstance(summary, list) and summary:
        for item in summary:
            lines.append(f"- {item}")
    else:
        lines.append("- [Summary]")
    lines.append("")
    lines.append("## Sources")
    if isinstance(sources, list) and sources:
        for entry in sources:
            if isinstance(entry, dict):
                description = str(entry.get("description") or entry.get("path") or entry.get("url") or "[Source]").strip()
                source_type = str(entry.get("type") or "source").strip()
                locator = str(entry.get("path") or entry.get("url") or "").strip()
                if locator:
                    lines.append(f"- `{source_type}`: {description} ({locator})")
                else:
                    lines.append(f"- `{source_type}`: {description}")
            else:
                lines.append(f"- {entry}")
    else:
        lines.append("- [Source]")
    lines.append("")
    lines.append("## Recommendation")
    if isinstance(recommendation, dict):
        for key in sorted(recommendation):
            lines.append(f"- {key}: {recommendation[key]}")
    elif recommendation is not None:
        lines.append(str(recommendation))
    else:
        lines.append("[Recommendation]")
    lines.append("")
    return "\n".join(lines)


def render_plan(plan: dict[str, Any]) -> str:
    feature = plan.get("feature", "[feature]")
    pn = plan.get("planNumber", "NN")
    goal = plan.get("goal", "")
    schema_version_raw = plan.get("schemaVersion", 1)
    schema_version = schema_version_raw if isinstance(schema_version_raw, int) and not isinstance(schema_version_raw, bool) else 1
    tasks = plan.get("tasks", []) if isinstance(plan.get("tasks"), list) else []
    plan_verify = plan.get("planVerify", [])
    commit_msg = plan.get("commitMessage", "")

    lines: list[str] = []
    lines.append(f"# Plan {pn}: {goal or '[Short Title]'}")
    lines.append("")
    lines.append("## Goal")
    lines.append(goal or "[One sentence: what this plan delivers]")
    lines.append("")
    lines.append("## Tasks")
    lines.append("")
    for i, t in enumerate(tasks, start=1):
        if not isinstance(t, dict):
            continue
        name = t.get("name", f"Task {i}")
        files = t.get("files", [])
        verify = t.get("verify", [])
        action = t.get("action", "")
        cwd = t.get("cwd")
        lines.append(f"### Task {i}: {name}")
        if cwd:
            lines.append(f"**CWD:** `{cwd}`")
        if isinstance(files, list) and files:
            lines.append("**Files:** " + ", ".join(f"`{f}`" for f in files))
        else:
            lines.append("**Files:** `[add files]`")
        lines.append("**Action:**")
        lines.append(action or "[Specific instructions]")
        lines.append("")
        if schema_version >= 2:
            micro_steps = t.get("microSteps", [])
            lines.append("**Micro-steps:**")
            if isinstance(micro_steps, list) and micro_steps:
                for step in micro_steps:
                    lines.append(f"- {step}")
            else:
                lines.append("- [Add microSteps[] entries]")
            lines.append("")

            tdd = t.get("tdd", {})
            lines.append("**TDD:**")
            if isinstance(tdd, dict):
                required = tdd.get("required")
                if required is True:
                    failing_verify = tdd.get("failingVerify", [])
                    passing_verify = tdd.get("passingVerify", [])
                    lines.append("- required: `true`")
                    lines.append("- failingVerify:")
                    if isinstance(failing_verify, list) and failing_verify:
                        for cmd in failing_verify:
                            lines.append(f"  - `{cmd}`")
                    else:
                        lines.append("  - `[add failingVerify command]`")
                    lines.append("- passingVerify:")
                    if isinstance(passing_verify, list) and passing_verify:
                        for cmd in passing_verify:
                            lines.append(f"  - `{cmd}`")
                    else:
                        lines.append("  - `[add passingVerify command]`")
                elif required is False:
                    lines.append("- required: `false`")
                    lines.append(f"- reason: {tdd.get('reason') or '[non-rationalized exemption reason]'}")
                else:
                    lines.append("- required: `[true|false]`")
            else:
                lines.append("- required: `[true|false]`")
            lines.append("")
        lines.append("**Verify:**")
        lines.append("```bash")
        if isinstance(verify, list) and verify:
            for v in verify:
                lines.append(str(v))
        else:
            lines.append("[Command to verify this task]")
        lines.append("```")
        lines.append("")
        lines.append("**Done when:** [Observable outcome]")
        lines.append("")

    lines.append("## Verification")
    lines.append("")
    lines.append("After all tasks:")
    lines.append("```bash")
    if isinstance(plan_verify, list) and plan_verify:
        for v in plan_verify:
            lines.append(str(v))
    else:
        lines.append("[Commands to verify the plan is complete]")
    lines.append("```")
    lines.append("")
    lines.append("## Commit Message")
    lines.append("```")
    lines.append(commit_msg or f"feat({feature}): [description]")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def render_summary(summary: dict[str, Any]) -> str:
    pn = summary.get("planNumber", "NN")
    outcome = summary.get("outcome", "complete")
    changes = summary.get("changes", [])
    verification = summary.get("verification", [])
    commit = summary.get("commit", {})

    lines: list[str] = []
    lines.append(f"# Plan {pn} Summary")
    lines.append("")
    lines.append("## Outcome")
    lines.append(f"{outcome}")
    lines.append("")
    lines.append("## Changes Made")
    lines.append("")
    lines.append("| File | Change |")
    lines.append("|------|--------|")
    if isinstance(changes, list) and changes:
        for c in changes:
            if isinstance(c, dict):
                lines.append(f"| `{c.get('file','')}` | {c.get('change','')} |")
    else:
        lines.append("| `path/to/file` | [what changed] |")
    lines.append("")
    lines.append("## Verification Results")
    lines.append("")
    if isinstance(verification, list) and verification:
        for v in verification:
            lines.append(f"- {v}")
    else:
        lines.append("- [verification results]")
    lines.append("")
    lines.append("## Commit")
    if isinstance(commit, dict):
        h = commit.get("hash", "")
        m = commit.get("message", "")
        lines.append(f"`{h}` - {m}".strip())
    else:
        lines.append("`abc123f` - [commit message]")
    lines.append("")
    return "\n".join(lines)


def render_quick_plan(plan: dict[str, Any]) -> str:
    """Render markdown for quick-task PLAN.json contracts."""
    goal = str(plan.get("goal", "")).strip()
    approach = str(plan.get("approach", "")).strip()
    files = plan.get("files", [])
    verify = plan.get("verify", [])

    lines: list[str] = []
    lines.append(f"# Quick: {goal or '[Quick task]'}")
    lines.append("")
    lines.append("## Goal")
    lines.append(goal or "[What this accomplishes]")
    lines.append("")
    lines.append("## Files")
    if isinstance(files, list) and files:
        for fp in files:
            lines.append(f"- `{fp}`")
    else:
        lines.append("- `path/to/file`")
    lines.append("")
    lines.append("## Approach")
    lines.append(approach or "[Brief description]")
    lines.append("")
    lines.append("## Verify")
    lines.append("```bash")
    if isinstance(verify, list) and verify:
        for v in verify:
            lines.append(str(v))
    else:
        lines.append("[How to verify]")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def render_quick_summary(summary: dict[str, Any]) -> str:
    """Render markdown for quick-task SUMMARY.json contracts."""
    outcome = str(summary.get("outcome", "complete"))
    changes = summary.get("changes", [])
    verification = summary.get("verification", [])
    commit = summary.get("commit", {})

    lines: list[str] = []
    lines.append("# Quick Summary")
    lines.append("")
    lines.append("## Outcome")
    lines.append(outcome)
    lines.append("")
    lines.append("## Changes")
    lines.append("| File | Change |")
    lines.append("|------|--------|")
    if isinstance(changes, list) and changes:
        for c in changes:
            if isinstance(c, dict):
                lines.append(f"| `{c.get('file','')}` | {c.get('change','')} |")
    else:
        lines.append("| `path/to/file` | [what changed] |")
    lines.append("")
    lines.append("## Verification")
    if isinstance(verification, list) and verification:
        for v in verification:
            lines.append(f"- {v}")
    else:
        lines.append("- [verification results]")
    lines.append("")
    lines.append("## Commit")
    if isinstance(commit, dict):
        h = commit.get("hash", "")
        m = commit.get("message", "")
        lines.append(f"`{h}` - {m}".strip())
    else:
        lines.append("`abc123f` - [commit message]")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render markdown artifacts from JSON contracts.")
    parser.add_argument("json_file", help="Path to JSON contract file.")
    args = parser.parse_args()

    jf = Path(args.json_file)
    if not jf.exists():
        raise SystemExit(f"File not found: {jf}")
    data = load_json(jf)
    if not isinstance(data, dict):
        raise SystemExit("Contract must be a JSON object.")

    if jf.name.endswith("-PLAN.json"):
        md = jf.with_name(jf.name.replace(".json", ".md"))
        write(md, render_plan(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name.endswith("-SUMMARY.json"):
        md = jf.with_name(jf.name.replace(".json", ".md"))
        write(md, render_summary(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name == "PLAN.json":
        md = jf.with_name("PLAN.md")
        write(md, render_quick_plan(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name == "SUMMARY.json":
        md = jf.with_name("SUMMARY.md")
        write(md, render_quick_summary(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name == "SHAPE.json":
        md = jf.with_name("SHAPE.md")
        write(md, render_shape(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name == "BRAINSTORM.json":
        md = jf.with_name("BRAINSTORM.md")
        write(md, render_brainstorm(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name == "FEATURE.json":
        md = jf.with_name("FEATURE.md")
        write(md, render_feature_stub(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name == "CONTEXT.json":
        md = jf.with_name("CONTEXT.md")
        write(md, render_context(data))
        print(f"✅ Rendered {md}")
        return 0
    if jf.name == "RESEARCH.json":
        md = jf.with_name("RESEARCH.md")
        write(md, render_research(data))
        print(f"✅ Rendered {md}")
        return 0

    raise SystemExit(
        (
            "Unsupported contract type. Use SHAPE.json, BRAINSTORM.json, FEATURE.json, CONTEXT.json, "
            "RESEARCH.json, *-PLAN.json, *-SUMMARY.json, PLAN.json, or SUMMARY.json."
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
