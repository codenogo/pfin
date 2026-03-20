#!/usr/bin/env python3
"""JSONL sync layer for the cnogo memory engine.

Provides export (SQLite -> .cnogo/issues.jsonl) and import (JSONL -> SQLite)
for git-portable state synchronization.

Format: one JSON object per line, sorted by ID for deterministic diffs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import storage as _st
from .graph import rebuild_blocked_cache
from .models import Dependency, Event

_CNOGO_DIR = ".cnogo"
_DB_NAME = "memory.db"
_JSONL_NAME = "issues.jsonl"

# Schema validation constants (W-4)
_VALID_STATUSES = frozenset({"open", "in_progress", "closed"})
_VALID_TYPES = frozenset({
    "epic", "plan", "task", "subtask", "bug", "quick", "background",
})


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically to avoid torn JSONL writes.

    Writes to a temp file in the same directory and replaces the destination.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def export_jsonl(root: Path) -> Path:
    """Export all issues from SQLite to .cnogo/issues.jsonl.

    Each line is a self-contained JSON object with deps, labels, and
    events inlined. Sorted by ID for stable, merge-friendly diffs.
    Returns the path to the JSONL file.
    """
    db_path = root / _CNOGO_DIR / _DB_NAME
    jsonl_path = root / _CNOGO_DIR / _JSONL_NAME

    conn = _st.connect(db_path)
    try:
        # Explicit read transaction for consistent WAL snapshot across all reads
        conn.execute("BEGIN")
        issues = _st.all_issues(conn)
        all_deps = _st.all_dependencies(conn)
        all_labels = _st.all_labels(conn)
        all_events = _st.all_events(conn)
        conn.execute("ROLLBACK")

        # Group deps by issue_id
        deps_by_issue: dict[str, list[dict[str, str]]] = {}
        for dep in all_deps:
            deps_by_issue.setdefault(dep.issue_id, []).append(dep.to_dict())

        # Group events by issue_id (B-1)
        events_by_issue: dict[str, list[dict[str, Any]]] = {}
        for event in all_events:
            events_by_issue.setdefault(event.issue_id, []).append(
                event.to_dict()
            )

        # Build JSONL lines
        lines: list[str] = []
        for issue in issues:
            d = issue.to_dict()
            # Inline deps, labels, and events
            if issue.id in deps_by_issue:
                d["deps"] = deps_by_issue[issue.id]
            if issue.id in all_labels:
                d["labels"] = all_labels[issue.id]
            if issue.id in events_by_issue:
                d["events"] = events_by_issue[issue.id]
            lines.append(json.dumps(d, sort_keys=True, separators=(",", ":")))

        _atomic_write_text(jsonl_path, "\n".join(lines) + "\n" if lines else "")
        return jsonl_path
    finally:
        conn.close()


def import_jsonl(root: Path) -> int:
    """Import .cnogo/issues.jsonl into SQLite.

    Upserts issues, recreates deps/labels/events, rebuilds blocked cache.
    Returns count of issues imported.
    """
    db_path = root / _CNOGO_DIR / _DB_NAME
    jsonl_path = root / _CNOGO_DIR / _JSONL_NAME

    if not jsonl_path.exists():
        return 0

    text = jsonl_path.read_text(encoding="utf-8").strip()
    if not text:
        return 0

    conn = _st.connect(db_path)
    _st.migrate(conn)  # ensure schema exists
    try:
        count = 0
        # First pass: import all issues (needed for FK validation on deps)
        parsed: list[tuple[int, dict[str, Any]]] = []
        for line_num, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"Warning: skipping malformed JSON at line {line_num}",
                    file=sys.stderr,
                )
                continue

            # Schema validation (W-4)
            try:
                issue = _obj_to_issue(obj)
            except ValueError as e:
                print(
                    f"Warning: skipping invalid issue at line {line_num}: {e}",
                    file=sys.stderr,
                )
                continue

            _st.upsert_issue(conn, issue)
            parsed.append((line_num, obj))
            count += 1

        issue_ids = [obj.get("id", "") for _, obj in parsed if isinstance(obj.get("id"), str)]
        existing_event_fps_by_issue = _existing_event_fingerprints_map(conn, issue_ids)

        # Second pass: import deps, labels, events (after all issues exist)
        for line_num, obj in parsed:
            issue_id = obj.get("id", "")

            # Recreate labels
            existing_labels = _st.get_labels(conn, issue_id)
            new_labels = obj.get("labels", [])
            for lbl in new_labels:
                if lbl not in existing_labels:
                    _st.add_label(conn, issue_id, lbl)

            # Recreate deps with FK validation (W-7)
            deps = obj.get("deps", [])
            for dep_obj in deps:
                depends_on = dep_obj.get("depends_on", "")
                dep_type = dep_obj.get("type", "blocks")
                if not depends_on:
                    continue
                if not _st.id_exists(conn, depends_on):
                    print(
                        f"Warning: skipping dep {issue_id} -> {depends_on}"
                        f" (target not found)",
                        file=sys.stderr,
                    )
                    continue
                dep = Dependency(
                    issue_id=issue_id,
                    depends_on_id=depends_on,
                    dep_type=dep_type,
                    created_at=obj.get("created_at", ""),
                )
                _st.insert_dependency(conn, dep)

            # Merge events by content fingerprint (issue_id + event fields).
            # This preserves remote tails without duplicating local history.
            events = obj.get("events", [])
            if isinstance(events, list) and events:
                existing_fingerprints = existing_event_fps_by_issue.setdefault(issue_id, set())
                for ev_obj in events:
                    if not isinstance(ev_obj, dict):
                        continue
                    ev_data = _normalize_event_data(ev_obj.get("data", {}))
                    fp = _event_fingerprint(
                        issue_id=issue_id,
                        event_type=ev_obj.get("event_type", ""),
                        actor=ev_obj.get("actor", ""),
                        created_at=ev_obj.get("created_at", ""),
                        data=ev_data,
                    )
                    if fp in existing_fingerprints:
                        continue
                    event = Event(
                        issue_id=issue_id,
                        event_type=ev_obj.get("event_type", ""),
                        actor=ev_obj.get("actor", ""),
                        data=ev_data,
                        created_at=ev_obj.get("created_at", ""),
                    )
                    _st.insert_event(conn, event)
                    existing_fingerprints.add(fp)

        rebuild_blocked_cache(conn)
        _rebuild_child_counters(conn)
        conn.commit()
        return count
    finally:
        conn.close()


def sync(root: Path) -> None:
    """Full sync: export JSONL, then git add the file."""
    jsonl_path = export_jsonl(root)

    # Stage the JSONL file for git
    try:
        subprocess.run(
            ["git", "add", "--", str(jsonl_path)],
            cwd=str(root),
            capture_output=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        pass  # Not in a git repo or git not available — that's fine


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_event_data(raw: Any) -> dict[str, Any]:
    """Normalize event data payload to a JSON object."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _event_fingerprint(
    *,
    issue_id: str,
    event_type: Any,
    actor: Any,
    created_at: Any,
    data: Any,
) -> tuple[str, str, str, str, str]:
    """Stable event identity tuple for deduplication during import."""
    norm = _normalize_event_data(data)
    payload = json.dumps(norm, sort_keys=True, separators=(",", ":"))
    return (
        issue_id,
        str(event_type or ""),
        str(actor or ""),
        str(created_at or ""),
        payload,
    )


def _existing_event_fingerprints(conn, issue_id: str) -> set[tuple[str, str, str, str, str]]:
    """Load existing event fingerprints for one issue."""
    rows = conn.execute(
        "SELECT event_type, actor, data, created_at FROM events WHERE issue_id = ?",
        (issue_id,),
    ).fetchall()
    return {
        _event_fingerprint(
            issue_id=issue_id,
            event_type=row["event_type"],
            actor=row["actor"],
            created_at=row["created_at"],
            data=row["data"],
        )
        for row in rows
    }


def _existing_event_fingerprints_map(
    conn,
    issue_ids: list[str],
) -> dict[str, set[tuple[str, str, str, str, str]]]:
    """Load existing event fingerprints for multiple issues in batches."""
    out: dict[str, set[tuple[str, str, str, str, str]]] = {}
    ids = [iid for iid in issue_ids if iid]
    if not ids:
        return out

    chunk_size = 500
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i:i + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            (
                "SELECT issue_id, event_type, actor, data, created_at "
                f"FROM events WHERE issue_id IN ({placeholders})"
            ),
            tuple(chunk),
        ).fetchall()
        for row in rows:
            issue_id = row["issue_id"]
            out.setdefault(issue_id, set()).add(
                _event_fingerprint(
                    issue_id=issue_id,
                    event_type=row["event_type"],
                    actor=row["actor"],
                    created_at=row["created_at"],
                    data=row["data"],
                )
            )

    return out


def _obj_to_issue(obj: dict[str, Any]) -> "Issue":
    """Parse a JSONL object into an Issue.

    Validates required fields and enum values (W-4).
    Raises ValueError on invalid data.
    """
    # Required fields
    issue_id = obj.get("id", "")
    title = obj.get("title", "")
    if not issue_id or not title:
        raise ValueError(f"Missing required fields: id={issue_id!r}, title={title!r}")

    # Enum validation
    status = obj.get("status", "open")
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")

    issue_type = obj.get("issue_type", "task")
    if issue_type not in _VALID_TYPES:
        raise ValueError(f"Invalid issue_type: {issue_type!r}")

    # Range validation
    priority = obj.get("priority", 2)
    if not isinstance(priority, int) or priority < 0 or priority > 4:
        raise ValueError(f"Invalid priority: {priority!r}")

    # Metadata
    meta = obj.get("metadata", {})
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}

    from .models import Issue as _Issue
    return _Issue(
        id=issue_id,
        content_hash=obj.get("content_hash", ""),
        title=title,
        description=obj.get("description", ""),
        status=status,
        state=obj.get("state", "open"),
        issue_type=issue_type,
        priority=priority,
        assignee=obj.get("assignee", ""),
        owner_actor=obj.get("owner_actor", ""),
        feature_slug=obj.get("feature_slug", ""),
        plan_number=obj.get("plan_number", ""),
        phase=_st.normalize_phase(obj.get("phase", "discuss")),
        close_reason=obj.get("close_reason", ""),
        metadata=meta if isinstance(meta, dict) else {},
        created_at=obj.get("created_at", ""),
        updated_at=obj.get("updated_at", ""),
        closed_at=obj.get("closed_at", ""),
    )


def _rebuild_child_counters(conn) -> None:
    """Rebuild child_counters table from existing hierarchical IDs."""
    conn.execute("DELETE FROM child_counters")
    # Find all issues whose ID contains a dot (hierarchical)
    rows = conn.execute(
        "SELECT id FROM issues WHERE id LIKE '%.%' ORDER BY id"
    ).fetchall()
    counters: dict[str, int] = {}
    for row in rows:
        issue_id = row["id"]
        # Parent is everything before the last dot
        last_dot = issue_id.rfind(".")
        if last_dot == -1:
            continue
        parent = issue_id[:last_dot]
        try:
            child_num = int(issue_id[last_dot + 1:])
        except ValueError:
            continue
        current_max = counters.get(parent, 0)
        if child_num >= current_max:
            counters[parent] = child_num + 1

    for parent_id, next_child in counters.items():
        conn.execute(
            "INSERT OR REPLACE INTO child_counters (parent_id, next_child)"
            " VALUES (?, ?)",
            (parent_id, next_child),
        )
