#!/usr/bin/env python3
"""Leader reconciliation algorithm for deterministic multi-agent closure.

Implements the bottom-up closure sequence: TASK -> PLAN -> EPIC.
Only the leader calls this — workers never close anything.

Algorithm:
1. Load epic and find all child PLANs.
2. For each PLAN, find all child TASKs.
3. Verify and close each TASK in done_by_worker state.
4. Close each PLAN when all its TASKs are closed.
5. Close EPIC when all PLANs are closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _set_ready_and_close(
    issue_id: str,
    *,
    actor: str = "leader",
    root: Path | None = None,
) -> None:
    """Set ready_to_close then close, with retry for SQLITE_BUSY."""
    from . import close
    from . import storage as _st

    r = root or Path(".")
    db_path = r / ".cnogo" / "memory.db"

    def _do() -> None:
        conn = _st.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _st.update_issue_fields(conn, issue_id, state="ready_to_close")
            conn.commit()
        finally:
            conn.close()

    _st.with_retry(_do)
    close(issue_id, actor_role="leader", actor=actor, root=root)


def reconcile(
    epic_id: str,
    *,
    actor: str = "leader",
    root: Path | None = None,
) -> dict[str, Any]:
    """Run deterministic leader reconciliation for an epic.

    Returns summary: {tasks_verified, tasks_closed, plans_closed,
    epic_closed, errors}.
    """
    # Late imports to avoid circular dependency
    from . import close, list_issues, show, verify_and_close
    from . import storage as _st

    summary: dict[str, Any] = {
        "tasks_verified": 0,
        "tasks_closed": 0,
        "plans_closed": 0,
        "epic_closed": False,
        "errors": [],
    }

    # Load epic
    epic = show(epic_id, root=root)
    if epic is None:
        summary["errors"].append(f"Epic {epic_id} not found")
        return summary

    # Find all PLANs under epic (parent-child dependency)
    plans = list_issues(
        issue_type="plan",
        parent=epic_id,
        limit=100,
        root=root,
    )

    all_plans_closed = True

    for plan in plans:
        # Find all TASKs under this PLAN
        tasks = list_issues(
            issue_type="task",
            parent=plan.id,
            limit=100,
            root=root,
        )

        all_tasks_closed = True

        for task in tasks:
            # Refresh task state
            fresh_task = show(task.id, root=root)
            if fresh_task is None:
                continue

            if fresh_task.state == "done_by_worker":
                try:
                    verify_and_close(task.id, actor=actor, root=root)
                    summary["tasks_verified"] += 1
                    summary["tasks_closed"] += 1
                except Exception as exc:
                    summary["errors"].append(
                        f"Failed to verify/close task {task.id}: {exc}"
                    )
                    all_tasks_closed = False
            elif fresh_task.state == "closed":
                summary["tasks_closed"] += 1
            else:
                all_tasks_closed = False

        # Close PLAN if all its TASKs are closed
        if all_tasks_closed and tasks:
            fresh_plan = show(plan.id, root=root)
            if fresh_plan and fresh_plan.state != "closed":
                try:
                    _set_ready_and_close(
                        plan.id, actor=actor, root=root,
                    )
                    summary["plans_closed"] += 1
                except Exception as exc:
                    summary["errors"].append(
                        f"Failed to close plan {plan.id}: {exc}"
                    )
                    all_plans_closed = False
            elif fresh_plan and fresh_plan.state == "closed":
                summary["plans_closed"] += 1
            else:
                all_plans_closed = False
        elif not tasks:
            # Plan with no tasks — check if already closed
            fresh_plan = show(plan.id, root=root)
            if fresh_plan and fresh_plan.state == "closed":
                summary["plans_closed"] += 1
            else:
                all_plans_closed = False
        else:
            all_plans_closed = False

    # Close EPIC if all PLANs are closed
    if all_plans_closed and plans:
        fresh_epic = show(epic_id, root=root)
        if fresh_epic and fresh_epic.state != "closed":
            try:
                _set_ready_and_close(
                    epic_id, actor=actor, root=root,
                )
                summary["epic_closed"] = True
            except Exception as exc:
                summary["errors"].append(
                    f"Failed to close epic {epic_id}: {exc}"
                )

    return summary
