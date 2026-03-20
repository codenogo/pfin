#!/usr/bin/env python3
"""Context generation for token-efficient agent consumption.

Generates minimal summaries (~500-1500 tokens) that agents can use
to understand current project state without reading full artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import storage as _st

_CNOGO_DIR = ".cnogo"
_DB_NAME = "memory.db"


def _conn(root: Path | None = None):  # noqa: ANN202
    r = root or Path(".")
    return _st.connect(r / _CNOGO_DIR / _DB_NAME)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _metadata_files(meta: dict) -> list[str]:
    raw = meta.get("files", [])
    if not isinstance(raw, list):
        return []
    return [f for f in raw if isinstance(f, str) and f.strip()]


def _latest_plan_json(root: Path, feature_slug: str) -> dict:
    base = root / "docs" / "planning" / "work" / "features" / feature_slug
    if not base.exists():
        return {}
    plan_files = sorted(
        p
        for p in base.glob("*-PLAN.json")
        if re.match(r"^[0-9]{2}-PLAN\.json$", p.name)
    )
    if not plan_files:
        return {}
    try:
        data = json.loads(plan_files[-1].read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _pick_feature_slug(conn, explicit_feature: str | None) -> str:
    if explicit_feature:
        return explicit_feature
    active = _st.list_issues_query(conn, status="in_progress", limit=50)
    for issue in active:
        if issue.feature_slug:
            return issue.feature_slug
    open_epics = _st.list_issues_query(
        conn, issue_type="epic", status="open", limit=50
    )
    for issue in open_epics:
        if issue.feature_slug:
            return issue.feature_slug
    return ""


def prime(
    *,
    limit: int = 10,
    verbose: bool = False,
    root: Path | None = None,
) -> str:
    """Generate minimal context summary for agent injection.

    Returns ~500-1500 tokens of structured markdown with:
    - Stats overview
    - In-progress work
    - Ready-to-start tasks
    """
    conn = _conn(root)
    try:
        s = _st.get_stats(conn)
        in_progress = _st.list_issues_query(
            conn, status="in_progress", limit=limit
        )
        ready_list = _st.ready_issues_query(conn, limit=limit)

        lines: list[str] = []

        # Header with stats
        open_count = s.get("open", 0)
        active = s.get("in_progress", 0)
        ready_count = s.get("ready", 0)
        blocked = s.get("blocked", 0)
        lines.append(
            f"## Memory: {open_count} open, {active} active,"
            f" {ready_count} ready, {blocked} blocked"
        )
        lines.append("")

        # Active Epics
        epics = _st.list_issues_query(
            conn, issue_type="epic", status="in_progress", limit=limit
        )
        if not epics:
            epics = _st.list_issues_query(
                conn, issue_type="epic", status="open", limit=limit
            )
        if epics:
            lines.append("### Active Epics")
            for epic in epics:
                children = _st.list_issues_query(
                    conn, parent=epic.id, limit=200
                )
                total = len(children)
                closed = sum(1 for c in children if c.status == "closed")
                slug = epic.feature_slug or epic.id
                plan = f" plan {epic.plan_number}" if epic.plan_number else ""
                progress = f" ({closed}/{total} tasks done)" if total else ""
                lines.append(
                    f"- `{epic.id}` **{slug}**{plan}{progress}"
                )
                handoff = epic.metadata.get("handoff", "")
                if handoff:
                    handoff_limit = 240 if verbose else 120
                    snippet = _truncate(str(handoff), handoff_limit)
                    lines.append(f"  Handoff: {snippet}")
            lines.append("")

        # In Progress
        if in_progress:
            lines.append("### In Progress")
            for issue in in_progress:
                assignee = f" (@{issue.assignee})" if issue.assignee else ""
                lines.append(
                    f"- `{issue.id}` {issue.title}{assignee}"
                )
                if verbose:
                    files = _metadata_files(issue.metadata)
                    if files:
                        shown = ", ".join(f"`{f}`" for f in files[:4])
                        lines.append(f"  Files: {shown}")
            lines.append("")

        # Ready
        if ready_list:
            lines.append("### Ready")
            for issue in ready_list:
                prio = f"[P{issue.priority}]"
                itype = f" ({issue.issue_type})" if issue.issue_type != "task" else ""
                lines.append(
                    f"- {prio} `{issue.id}` {issue.title}{itype}"
                )
                if verbose:
                    files = _metadata_files(issue.metadata)
                    if files:
                        shown = ", ".join(f"`{f}`" for f in files[:3])
                        lines.append(f"  Files: {shown}")
            lines.append("")

        # By Feature summary
        by_feature = s.get("by_feature", {})
        if by_feature:
            lines.append("### Features")
            for slug, count in sorted(by_feature.items()):
                lines.append(f"- `{slug}`: {count} open")
            lines.append("")

        lines.append("### Restore")
        lines.append("Details: `python3 .cnogo/scripts/workflow_memory.py show <id>`")
        if verbose:
            lines.append("History: `python3 .cnogo/scripts/workflow_memory.py history <id>`")
            lines.append("Checkpoint: `python3 .cnogo/scripts/workflow_memory.py checkpoint`")
        lines.append("")

        return "\n".join(lines)
    finally:
        conn.close()


def checkpoint(
    *,
    feature_slug: str | None = None,
    limit: int = 3,
    root: Path | None = None,
) -> str:
    """Return a compact objective/progress checkpoint for recitation."""
    conn = _conn(root)
    try:
        feature = _pick_feature_slug(conn, feature_slug)
        if not feature:
            return (
                "Checkpoint: no active feature in memory. "
                "Run `python3 .cnogo/scripts/workflow_memory.py prime --verbose`."
            )

        issues = _st.list_issues_query(conn, feature_slug=feature, limit=300)
        tasks = [i for i in issues if i.issue_type != "epic"]
        total = len(tasks)
        done = sum(1 for i in tasks if i.status == "closed")
        active = [i for i in tasks if i.status == "in_progress"]
        remaining = [i for i in tasks if i.status != "closed"]
        phase = _st.get_feature_phase(conn, feature)

        r = root or Path(".")
        plan = _latest_plan_json(r, feature)
        goal = str(plan.get("goal", "")).strip() if isinstance(plan, dict) else ""
        verify = plan.get("planVerify", []) if isinstance(plan, dict) else []
        verify_cmds = [
            v for v in verify if isinstance(v, str) and v.strip()
        ]

        lines: list[str] = []
        lines.append(
            f"Checkpoint: `{feature}` phase={phase}, "
            f"progress={done}/{total} done, active={len(active)}, "
            f"remaining={len(remaining)}"
        )
        if goal:
            lines.append(f"Objective: {_truncate(goal, 180)}")
        if active:
            current = "; ".join(
                f"{i.id} {_truncate(i.title, 60)}" for i in active[:limit]
            )
            lines.append(f"Current: {current}")
        elif remaining:
            nxt = "; ".join(
                f"{i.id} {_truncate(i.title, 60)}" for i in remaining[:limit]
            )
            lines.append(f"Next: {nxt}")
        if verify_cmds:
            lines.append(
                "Verify: " + "; ".join(_truncate(v, 80) for v in verify_cmds[:2])
            )
        lines.append("Refresh: `python3 .cnogo/scripts/workflow_memory.py prime --limit 5 --verbose`")
        return "\n".join(lines)
    finally:
        conn.close()


def history(issue_id: str, *, limit: int = 10, root: Path | None = None) -> str:
    """Return formatted event history for one issue."""
    conn = _conn(root)
    try:
        issue = _st.get_issue(conn, issue_id)
        if issue is None:
            return f"Issue {issue_id!r} not found."
        events = _st.get_events(conn, issue_id, limit=limit)
        if not events:
            return f"History for `{issue.id}` ({issue.title}): no events."

        lines = [f"History for `{issue.id}` ({issue.title})", ""]
        for ev in reversed(events):
            payload = json.dumps(
                ev.data or {}, sort_keys=True, separators=(",", ":")
            )
            payload = _truncate(payload, 200)
            lines.append(
                f"- [{ev.created_at}] {ev.event_type} by {ev.actor or 'unknown'} data={payload}"
            )
        return "\n".join(lines)
    finally:
        conn.close()


def show_graph(feature_slug: str, *, root: Path | None = None) -> str:
    """Render ASCII dependency graph for a feature.

    Returns a text representation of the issue hierarchy and dependencies.
    """
    conn = _conn(root)
    try:
        issues = _st.list_issues_query(
            conn, feature_slug=feature_slug, limit=200
        )
        if not issues:
            return f"No issues found for feature '{feature_slug}'."

        # Build ID->Issue map
        issue_map = {i.id: i for i in issues}

        # Find parent-child relationships
        children: dict[str, list[str]] = {}
        has_parent: set[str] = set()
        blocking: dict[str, list[str]] = {}

        for issue in issues:
            deps = _st.get_dependencies(conn, issue.id)
            for dep in deps:
                if dep.dep_type == "parent-child":
                    children.setdefault(dep.depends_on_id, []).append(issue.id)
                    has_parent.add(issue.id)
                elif dep.dep_type == "blocks":
                    blocking.setdefault(dep.depends_on_id, []).append(issue.id)

        # Root issues: those without a parent (within this feature)
        roots = [i.id for i in issues if i.id not in has_parent]
        roots.sort()

        lines: list[str] = [f"## {feature_slug} Dependency Graph", ""]

        def _render(issue_id: str, indent: int = 0) -> None:
            issue = issue_map.get(issue_id)
            if not issue:
                return
            prefix = "  " * indent
            status_icon = {
                "open": " ",
                "in_progress": ">",
                "closed": "x",
            }.get(issue.status, "?")
            lines.append(
                f"{prefix}[{status_icon}] {issue.id} {issue.title}"
            )
            # Show blocking relationships
            for blocked in blocking.get(issue_id, []):
                if blocked in issue_map:
                    bi = issue_map[blocked]
                    lines.append(
                        f"{prefix}    -> blocks {blocked} {bi.title}"
                    )
            # Recurse into children
            for child_id in sorted(children.get(issue_id, [])):
                _render(child_id, indent + 1)

        for root_id in roots:
            _render(root_id)

        return "\n".join(lines)
    finally:
        conn.close()
