#!/usr/bin/env python3
"""Agent health monitoring — stale task and issue detection.

On-demand checks (no background daemon). Called by /doctor and
can be run standalone. Python stdlib only.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SESSION_FILE = ".cnogo/worktree-session.json"
_DB_NAME = "memory.db"
_CNOGO_DIR = ".cnogo"

_TERMINAL_STATUSES = frozenset({"merged", "conflict", "cleaned"})


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now_utc().isoformat()


def check_stale_tasks(root: Path, stale_minutes: int = 10) -> list[dict]:
    """Check for stale executing tasks in worktree sessions.

    Reads .cnogo/worktree-session.json and returns worktrees that are
    not in a terminal status and whose session file has not been updated
    within stale_minutes.

    Returns list of dicts: {task_index, name, branch, minutes_stale, memory_id}.
    Returns empty list if no session file exists.
    """
    session_path = root / _SESSION_FILE
    if not session_path.exists():
        return []

    try:
        mtime = session_path.stat().st_mtime
    except OSError:
        return []

    try:
        with session_path.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    worktrees = data.get("worktrees", [])
    if not worktrees:
        return []

    now = _now_utc().timestamp()
    age_minutes = (now - mtime) / 60.0

    if age_minutes < stale_minutes:
        return []

    stale = []
    for wt in worktrees:
        status = wt.get("status", "")
        if status in _TERMINAL_STATUSES:
            continue
        stale.append({
            "task_index": wt.get("taskIndex", wt.get("task_index", 0)),
            "name": wt.get("name", ""),
            "branch": wt.get("branch", ""),
            "minutes_stale": round(age_minutes, 1),
            "memory_id": wt.get("memoryId", wt.get("memory_id", "")),
        })

    return stale


def check_stale_issues(root: Path, stale_days: int = 30) -> list[dict]:
    """Check for stale open issues with no assignee.

    Queries .cnogo/memory.db for open issues with no assignee that were
    created more than stale_days ago.

    Returns list of dicts: {id, title, days_stale}.
    Returns empty list if DB doesn't exist.
    """
    db_path = root / _CNOGO_DIR / _DB_NAME
    if not db_path.exists():
        return []

    cutoff = (_now_utc() - timedelta(days=stale_days)).isoformat()

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT id, title, created_at FROM issues
                   WHERE status = 'open'
                   AND (assignee IS NULL OR assignee = '')
                   AND created_at < ?""",
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []

    now = _now_utc()
    stale = []
    for row in rows:
        try:
            created = datetime.fromisoformat(row["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days_stale = (now - created).days
        except (ValueError, TypeError):
            days_stale = stale_days

        stale.append({
            "id": row["id"],
            "title": row["title"],
            "days_stale": days_stale,
        })

    return stale


def record_stale_event(
    root: Path,
    stale_info: list[dict],
    actor: str = "watchdog",
) -> None:
    """Record stale_detected events in memory.db for each stale item.

    Handles gracefully if DB doesn't exist or insert fails.
    """
    db_path = root / _CNOGO_DIR / _DB_NAME
    if not db_path.exists():
        return
    if not stale_info:
        return

    try:
        conn = sqlite3.connect(str(db_path))
        try:
            now = _iso_now()
            for item in stale_info:
                issue_id = item.get("id") or item.get("memory_id") or ""
                if not issue_id:
                    continue
                data = json.dumps({k: v for k, v in item.items() if k != "id"})
                conn.execute(
                    """INSERT INTO events
                       (issue_id, event_type, actor, data, created_at)
                       VALUES (?, 'stale_detected', ?, ?, ?)""",
                    (issue_id, actor, data, now),
                )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def run_all_checks(root: Path, config: dict | None = None) -> dict:
    """Run all health monitoring checks.

    config may contain keys:
      - staleIndicatorMinutes (int): threshold for stale tasks (default 10)
      - contextMaxAgeDays (int): threshold for stale issues (default 30)

    Returns {stale_tasks, stale_issues, checked_at}.
    """
    cfg = config or {}
    stale_minutes = int(cfg.get("staleIndicatorMinutes", 10))
    stale_days = int(cfg.get("contextMaxAgeDays", 30))

    stale_tasks = check_stale_tasks(root, stale_minutes)
    stale_issues = check_stale_issues(root, stale_days)

    return {
        "stale_tasks": stale_tasks,
        "stale_issues": stale_issues,
        "checked_at": _iso_now(),
    }
