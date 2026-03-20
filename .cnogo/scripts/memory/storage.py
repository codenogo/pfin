#!/usr/bin/env python3
"""SQLite storage operations for the cnogo memory engine.

WAL mode for concurrent reads, foreign keys for referential integrity.
All timestamps are UTC ISO-8601. No external dependencies.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Dependency, Event, Issue

SCHEMA_VERSION = 3
WORKFLOW_PHASES = ("discuss", "plan", "implement", "review", "ship")
_VALID_PHASES = frozenset(WORKFLOW_PHASES)

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS issues (
    id TEXT PRIMARY KEY,
    content_hash TEXT DEFAULT '',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'open'
        CHECK(status IN ('open', 'in_progress', 'closed')),
    state TEXT DEFAULT 'open'
        CHECK(state IN ('open', 'in_progress', 'done_by_worker', 'verified', 'closed', 'ready_to_close')),
    issue_type TEXT DEFAULT 'task'
        CHECK(issue_type IN ('epic', 'plan', 'task', 'subtask', 'bug', 'quick', 'background')),
    priority INTEGER DEFAULT 2
        CHECK(priority >= 0 AND priority <= 4),
    assignee TEXT DEFAULT '',
    owner_actor TEXT DEFAULT '',
    feature_slug TEXT DEFAULT '',
    plan_number TEXT DEFAULT '',
    phase TEXT DEFAULT 'discuss'
        CHECK(phase IN ('discuss', 'plan', 'implement', 'review', 'ship')),
    close_reason TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS dependencies (
    issue_id TEXT NOT NULL,
    depends_on_id TEXT NOT NULL,
    dep_type TEXT DEFAULT 'blocks'
        CHECK(dep_type IN ('blocks', 'parent-child', 'related', 'discovered-from')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (issue_id, depends_on_id),
    FOREIGN KEY (issue_id) REFERENCES issues(id),
    FOREIGN KEY (depends_on_id) REFERENCES issues(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT DEFAULT '',
    data TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);

CREATE TABLE IF NOT EXISTS labels (
    issue_id TEXT NOT NULL,
    label TEXT NOT NULL,
    PRIMARY KEY (issue_id, label),
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);

CREATE TABLE IF NOT EXISTS blocked_cache (
    issue_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS child_counters (
    parent_id TEXT PRIMARY KEY,
    next_child INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS schema_info (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_type ON issues(issue_type);
CREATE INDEX IF NOT EXISTS idx_issues_feature ON issues(feature_slug);
CREATE INDEX IF NOT EXISTS idx_issues_assignee ON issues(assignee);
CREATE INDEX IF NOT EXISTS idx_issues_priority ON issues(priority);
CREATE INDEX IF NOT EXISTS idx_deps_depends_on ON dependencies(depends_on_id);
CREATE INDEX IF NOT EXISTS idx_deps_type ON dependencies(dep_type);
CREATE INDEX IF NOT EXISTS idx_events_issue ON events(issue_id);
CREATE INDEX IF NOT EXISTS idx_labels_label ON labels(label);
"""


# ---------------------------------------------------------------------------
# Table allowlist (defense-in-depth for PRAGMA calls)
# ---------------------------------------------------------------------------

_ALLOWED_TABLES = frozenset({
    "issues", "dependencies", "events", "labels",
    "blocked_cache", "child_counters", "schema_info",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """UTC ISO-8601 timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return {}


def normalize_phase(phase: str | None) -> str:
    """Normalize and validate a workflow phase string."""
    p = (phase or "discuss").strip().lower()
    if p not in _VALID_PHASES:
        raise ValueError(
            f"Invalid phase {phase!r}. Expected one of {sorted(_VALID_PHASES)}"
        )
    return p


def validate_phase_transition(current: str, target: str) -> bool:
    """Check if a phase transition is forward-only.

    Returns True if the transition is valid (forward or idempotent).
    Prints a stderr warning and returns False for backward transitions.
    Advisory mode: callers should proceed regardless.
    """
    cur_idx = WORKFLOW_PHASES.index(normalize_phase(current))
    tgt_idx = WORKFLOW_PHASES.index(normalize_phase(target))
    if tgt_idx < cur_idx:
        print(
            f"[cnogo] Warning: backward phase transition "
            f"{current!r} -> {target!r} (advisory)",
            file=sys.stderr,
        )
        return False
    return True


def _row_to_issue(row: sqlite3.Row) -> Issue:
    keys = row.keys()
    return Issue(
        id=row["id"],
        content_hash=row["content_hash"] or "",
        title=row["title"],
        description=row["description"] or "",
        status=row["status"],
        state=row["state"] if "state" in keys else "open",
        issue_type=row["issue_type"],
        priority=row["priority"],
        assignee=row["assignee"] or "",
        owner_actor=row["owner_actor"] if "owner_actor" in keys else "",
        feature_slug=row["feature_slug"] or "",
        plan_number=row["plan_number"] or "",
        phase=normalize_phase(
            row["phase"] if "phase" in keys else "discuss"
        ),
        close_reason=row["close_reason"] or "",
        metadata=_parse_json(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        closed_at=row["closed_at"] or "",
    )


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        issue_id=row["issue_id"],
        event_type=row["event_type"],
        actor=row["actor"] or "",
        data=_parse_json(row["data"]),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Retry helper for SQLITE_BUSY
# ---------------------------------------------------------------------------

def with_retry(fn, *args, max_retries=3, base_delay=0.1, **kwargs):
    """Call *fn* with retry on SQLITE_BUSY (database is locked).

    Uses exponential backoff: base_delay * 2^attempt (0.1s, 0.2s, 0.4s).
    Re-raises after *max_retries* failures. Stdlib only (time.sleep).
    """
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc):
                raise
            if attempt == max_retries:
                raise
            time.sleep(base_delay * (2 ** attempt))


# ---------------------------------------------------------------------------
# Connection & Migration
# ---------------------------------------------------------------------------

def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite connection with WAL mode and pragmas."""
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Create or upgrade schema to current version."""
    conn.executescript(SCHEMA_SQL)
    current = _current_schema_version(conn)
    if current < 2:
        _migrate_to_v2(conn)
        current = 2
    if current < 3:
        _migrate_to_v3(conn)
        current = 3
    if _column_exists(conn, "issues", "phase"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_phase ON issues(phase)")
    conn.execute(
        "INSERT OR REPLACE INTO schema_info (key, value) VALUES (?, ?)",
        ("version", str(max(current, SCHEMA_VERSION))),
    )
    conn.commit()


def _current_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM schema_info WHERE key = 'version'"
    ).fetchone()
    if row is None:
        return 1
    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return 1


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Unknown table: {table!r}")
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
    return any(r["name"] == column for r in rows)


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Schema v2: add workflow phase to issues."""
    if not _column_exists(conn, "issues", "phase"):
        try:
            conn.execute(
                "ALTER TABLE issues ADD COLUMN phase TEXT DEFAULT 'discuss'"
            )
        except sqlite3.OperationalError as exc:
            # Concurrent migrators may race to add the same column.
            if "duplicate column name" not in str(exc).lower():
                raise
    conn.execute("UPDATE issues SET phase = 'ship' WHERE status = 'closed'")


def _migrate_to_v3(conn: sqlite3.Connection) -> None:
    """Schema v3: add state and owner_actor columns for deterministic coordination."""
    if not _column_exists(conn, "issues", "state"):
        try:
            conn.execute(
                "ALTER TABLE issues ADD COLUMN state TEXT DEFAULT 'open'"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    if not _column_exists(conn, "issues", "owner_actor"):
        try:
            conn.execute(
                "ALTER TABLE issues ADD COLUMN owner_actor TEXT DEFAULT ''"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    # Backfill state from status
    conn.execute("UPDATE issues SET state = 'closed' WHERE status = 'closed' AND state = 'open'")
    conn.execute("UPDATE issues SET state = 'in_progress' WHERE status = 'in_progress' AND state = 'open'")
    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_state ON issues(state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_owner ON issues(owner_actor)")


# ---------------------------------------------------------------------------
# Issue CRUD
# ---------------------------------------------------------------------------

def insert_issue(conn: sqlite3.Connection, issue: Issue) -> None:
    phase = normalize_phase(getattr(issue, "phase", "discuss"))
    state = getattr(issue, "state", "open") or "open"
    owner_actor = getattr(issue, "owner_actor", "") or ""
    conn.execute(
        """INSERT INTO issues
           (id, content_hash, title, description, status, state, issue_type,
            priority, assignee, owner_actor, feature_slug, plan_number, phase,
            close_reason, metadata, created_at, updated_at, closed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            issue.id, issue.content_hash, issue.title, issue.description,
            issue.status, state, issue.issue_type, issue.priority,
            issue.assignee, owner_actor, issue.feature_slug,
            issue.plan_number, phase, issue.close_reason,
            json.dumps(issue.metadata, sort_keys=True, separators=(",", ":")),
            issue.created_at, issue.updated_at,
            issue.closed_at,
        ),
    )


def upsert_issue(conn: sqlite3.Connection, issue: Issue) -> None:
    """Insert or replace (for JSONL import)."""
    phase = normalize_phase(getattr(issue, "phase", "discuss"))
    state = getattr(issue, "state", "open") or "open"
    owner_actor = getattr(issue, "owner_actor", "") or ""
    conn.execute(
        """INSERT OR REPLACE INTO issues
           (id, content_hash, title, description, status, state, issue_type,
            priority, assignee, owner_actor, feature_slug, plan_number, phase,
            close_reason, metadata, created_at, updated_at, closed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            issue.id, issue.content_hash, issue.title, issue.description,
            issue.status, state, issue.issue_type, issue.priority,
            issue.assignee, owner_actor, issue.feature_slug,
            issue.plan_number, phase, issue.close_reason,
            json.dumps(issue.metadata, sort_keys=True, separators=(",", ":")),
            issue.created_at, issue.updated_at,
            issue.closed_at,
        ),
    )


def get_issue(conn: sqlite3.Connection, issue_id: str) -> Issue | None:
    row = conn.execute(
        "SELECT * FROM issues WHERE id = ?", (issue_id,)
    ).fetchone()
    return _row_to_issue(row) if row else None


def id_exists(conn: sqlite3.Connection, issue_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM issues WHERE id = ?", (issue_id,)
    ).fetchone()
    return row is not None


_ALLOWED_FIELDS = frozenset({
    "content_hash", "title", "description", "status", "state", "issue_type",
    "priority", "assignee", "owner_actor", "feature_slug", "plan_number",
    "phase", "close_reason", "metadata", "closed_at", "updated_at",
})


def update_issue_fields(
    conn: sqlite3.Connection, issue_id: str, **fields: Any
) -> bool:
    """Update arbitrary fields on an issue. Returns True if a row was modified."""
    if not fields:
        return False
    # Validate field names against whitelist to prevent SQL injection
    invalid = set(fields.keys()) - _ALLOWED_FIELDS
    if invalid:
        raise ValueError(f"Invalid fields: {invalid}")
    fields["updated_at"] = _now()
    # Serialize metadata to JSON string if present
    if "metadata" in fields and isinstance(fields["metadata"], dict):
        fields["metadata"] = json.dumps(
            fields["metadata"], sort_keys=True, separators=(",", ":")
        )
    if "phase" in fields:
        fields["phase"] = normalize_phase(str(fields["phase"]))
    # Safe: field names are validated against _ALLOWED_FIELDS above
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [issue_id]
    cursor = conn.execute(
        f"UPDATE issues SET {set_clause} WHERE id = ?", values  # noqa: S608
    )
    return cursor.rowcount > 0


def claim_issue(conn: sqlite3.Connection, issue_id: str, actor: str) -> bool:
    """Atomic compare-and-swap claim. Returns True if claimed successfully.

    Caller should use BEGIN IMMEDIATE for proper write-lock isolation
    in multi-agent scenarios.
    """
    now = _now()
    cursor = conn.execute(
        """UPDATE issues
           SET assignee = ?, status = 'in_progress', updated_at = ?
           WHERE id = ? AND (assignee IS NULL OR assignee = '')""",
        (actor, now, issue_id),
    )
    return cursor.rowcount > 0


def close_issue(conn: sqlite3.Connection, issue_id: str, reason: str) -> bool:
    """Close an issue. Returns True if status changed."""
    now = _now()
    cursor = conn.execute(
        """UPDATE issues
           SET status = 'closed', close_reason = ?, closed_at = ?, updated_at = ?
           WHERE id = ? AND status != 'closed'""",
        (reason, now, now, issue_id),
    )
    return cursor.rowcount > 0


def release_issue(conn: sqlite3.Connection, issue_id: str) -> bool:
    """Release a claimed (in_progress) issue back to open/unassigned.

    Used when an agent dies or a task needs to be re-assigned.
    Returns True if status changed.
    """
    now = _now()
    cursor = conn.execute(
        """UPDATE issues
           SET status = 'open', assignee = '', updated_at = ?
           WHERE id = ? AND status = 'in_progress'""",
        (now, issue_id),
    )
    return cursor.rowcount > 0


def reopen_issue(conn: sqlite3.Connection, issue_id: str) -> bool:
    """Reopen a closed issue. Returns True if status changed."""
    now = _now()
    cursor = conn.execute(
        """UPDATE issues
           SET status = 'open', closed_at = '', close_reason = '',
               assignee = '', updated_at = ?
           WHERE id = ? AND status = 'closed'""",
        (now, issue_id),
    )
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Dependency CRUD
# ---------------------------------------------------------------------------

def insert_dependency(conn: sqlite3.Connection, dep: Dependency) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO dependencies
           (issue_id, depends_on_id, dep_type, created_at)
           VALUES (?, ?, ?, ?)""",
        (dep.issue_id, dep.depends_on_id, dep.dep_type, dep.created_at),
    )


def remove_dependency(
    conn: sqlite3.Connection, issue_id: str, depends_on_id: str
) -> bool:
    cursor = conn.execute(
        "DELETE FROM dependencies WHERE issue_id = ? AND depends_on_id = ?",
        (issue_id, depends_on_id),
    )
    return cursor.rowcount > 0


def get_dependencies(
    conn: sqlite3.Connection, issue_id: str
) -> list[Dependency]:
    """Get all dependencies where issue_id is the blocked issue."""
    rows = conn.execute(
        "SELECT * FROM dependencies WHERE issue_id = ?", (issue_id,)
    ).fetchall()
    return [
        Dependency(
            issue_id=r["issue_id"],
            depends_on_id=r["depends_on_id"],
            dep_type=r["dep_type"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def get_blocked_by(conn: sqlite3.Connection, issue_id: str) -> list[Issue]:
    """Get open issues that directly block this one ('blocks' type only).

    Parent-child deps are not direct blockers — they only propagate
    transitively through the blocked cache.
    """
    rows = conn.execute(
        """SELECT i.* FROM issues i
           JOIN dependencies d ON i.id = d.depends_on_id
           WHERE d.issue_id = ?
             AND d.dep_type = 'blocks'
             AND i.status != 'closed'""",
        (issue_id,),
    ).fetchall()
    return [_row_to_issue(r) for r in rows]


def get_blocks(conn: sqlite3.Connection, issue_id: str) -> list[Issue]:
    """Get issues that this one directly blocks ('blocks' type only)."""
    rows = conn.execute(
        """SELECT i.* FROM issues i
           JOIN dependencies d ON i.id = d.issue_id
           WHERE d.depends_on_id = ?
             AND d.dep_type = 'blocks'""",
        (issue_id,),
    ).fetchall()
    return [_row_to_issue(r) for r in rows]


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------

def insert_event(conn: sqlite3.Connection, event: Event) -> int:
    cursor = conn.execute(
        """INSERT INTO events (issue_id, event_type, actor, data, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            event.issue_id, event.event_type, event.actor,
            json.dumps(event.data, sort_keys=True, separators=(",", ":")),
            event.created_at,
        ),
    )
    return cursor.lastrowid or 0


def get_events(
    conn: sqlite3.Connection, issue_id: str, *, limit: int = 20
) -> list[Event]:
    rows = conn.execute(
        "SELECT * FROM events WHERE issue_id = ? ORDER BY id DESC LIMIT ?",
        (issue_id, limit),
    ).fetchall()
    return [_row_to_event(r) for r in rows]


# ---------------------------------------------------------------------------
# Label CRUD
# ---------------------------------------------------------------------------

def add_label(conn: sqlite3.Connection, issue_id: str, label: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO labels (issue_id, label) VALUES (?, ?)",
        (issue_id, label),
    )


def remove_label(
    conn: sqlite3.Connection, issue_id: str, label: str
) -> bool:
    cursor = conn.execute(
        "DELETE FROM labels WHERE issue_id = ? AND label = ?",
        (issue_id, label),
    )
    return cursor.rowcount > 0


def get_labels(conn: sqlite3.Connection, issue_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT label FROM labels WHERE issue_id = ? ORDER BY label",
        (issue_id,),
    ).fetchall()
    return [r["label"] for r in rows]


# ---------------------------------------------------------------------------
# Child Counters
# ---------------------------------------------------------------------------

def next_child_number(conn: sqlite3.Connection, parent_id: str) -> int:
    """Get-and-increment the child counter for a parent issue.

    Caller must hold a write lock (BEGIN IMMEDIATE) for atomicity
    in multi-process scenarios.
    """
    # Ensure counter row exists
    conn.execute(
        "INSERT OR IGNORE INTO child_counters (parent_id, next_child)"
        " VALUES (?, 1)",
        (parent_id,),
    )
    # Read current value
    row = conn.execute(
        "SELECT next_child FROM child_counters WHERE parent_id = ?",
        (parent_id,),
    ).fetchone()
    num = row["next_child"]
    # Increment
    conn.execute(
        "UPDATE child_counters SET next_child = ? WHERE parent_id = ?",
        (num + 1, parent_id),
    )
    return num


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def list_issues_query(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    issue_type: str | None = None,
    feature_slug: str | None = None,
    parent: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    limit: int = 100,
) -> list[Issue]:
    """List issues with optional filters."""
    conditions: list[str] = []
    params: list[Any] = []

    if status is not None:
        conditions.append("i.status = ?")
        params.append(status)
    if issue_type is not None:
        conditions.append("i.issue_type = ?")
        params.append(issue_type)
    if feature_slug is not None:
        conditions.append("i.feature_slug = ?")
        params.append(feature_slug)
    if assignee is not None:
        conditions.append("i.assignee = ?")
        params.append(assignee)
    if label is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM labels l"
            " WHERE l.issue_id = i.id AND l.label = ?)"
        )
        params.append(label)
    if parent is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM dependencies d"
            " WHERE d.issue_id = i.id"
            " AND d.depends_on_id = ?"
            " AND d.dep_type = 'parent-child')"
        )
        params.append(parent)

    where = " AND ".join(conditions) if conditions else "1=1"
    params.append(limit)

    rows = conn.execute(
        f"SELECT i.* FROM issues i"  # noqa: S608
        f" WHERE {where}"
        f" ORDER BY i.priority ASC, i.created_at ASC"
        f" LIMIT ?",
        params,
    ).fetchall()
    return [_row_to_issue(r) for r in rows]


def ready_issues_query(
    conn: sqlite3.Connection,
    *,
    assignee: str | None = None,
    feature_slug: str | None = None,
    label: str | None = None,
    limit: int = 20,
) -> list[Issue]:
    """Get unblocked, open issues ready for work."""
    conditions = [
        "i.status = 'open'",
        "i.id NOT IN (SELECT issue_id FROM blocked_cache)",
    ]
    params: list[Any] = []

    if assignee is not None:
        conditions.append("i.assignee = ?")
        params.append(assignee)
    if feature_slug is not None:
        conditions.append("i.feature_slug = ?")
        params.append(feature_slug)
    if label is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM labels l"
            " WHERE l.issue_id = i.id AND l.label = ?)"
        )
        params.append(label)

    where = " AND ".join(conditions)
    params.append(limit)

    rows = conn.execute(
        f"SELECT i.* FROM issues i"  # noqa: S608
        f" WHERE {where}"
        f" ORDER BY i.priority ASC, i.created_at ASC"
        f" LIMIT ?",
        params,
    ).fetchall()
    return [_row_to_issue(r) for r in rows]


def get_feature_phase(conn: sqlite3.Connection, feature_slug: str) -> str:
    """Get the latest workflow phase for a feature (defaults to discuss)."""
    if not feature_slug:
        return "discuss"
    row = conn.execute(
        """SELECT phase FROM issues
           WHERE feature_slug = ?
           ORDER BY updated_at DESC
           LIMIT 1""",
        (feature_slug,),
    ).fetchone()
    if row is None:
        return "discuss"
    return normalize_phase(row["phase"] if row["phase"] else "discuss")


def set_feature_phase(
    conn: sqlite3.Connection,
    feature_slug: str,
    phase: str,
) -> int:
    """Set workflow phase for all issues in a feature. Returns row count."""
    if not feature_slug:
        return 0
    normalized = normalize_phase(phase)
    current = get_feature_phase(conn, feature_slug)
    validate_phase_transition(current, normalized)  # advisory — always proceeds
    cursor = conn.execute(
        "UPDATE issues SET phase = ?, updated_at = ? WHERE feature_slug = ?",
        (normalized, _now(), feature_slug),
    )
    return cursor.rowcount


def get_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Aggregate statistics across all issues.

    Uses an explicit read transaction for a consistent snapshot
    across multiple queries.
    """
    # Start a read transaction so all queries see the same snapshot
    conn.execute("BEGIN")
    try:
        s: dict[str, Any] = {}

        for row in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM issues GROUP BY status"
        ):
            s[row["status"]] = row["cnt"]

        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM issues"
            " WHERE status = 'open'"
            " AND id NOT IN (SELECT issue_id FROM blocked_cache)"
        ).fetchone()
        s["ready"] = row["cnt"] if row else 0

        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM blocked_cache"
        ).fetchone()
        s["blocked"] = row["cnt"] if row else 0

        by_type: dict[str, int] = {}
        for row in conn.execute(
            "SELECT issue_type, COUNT(*) as cnt FROM issues"
            " WHERE status != 'closed' GROUP BY issue_type"
        ):
            by_type[row["issue_type"]] = row["cnt"]
        s["by_type"] = by_type

        by_feature: dict[str, int] = {}
        for row in conn.execute(
            "SELECT feature_slug, COUNT(*) as cnt FROM issues"
            " WHERE status != 'closed' AND feature_slug != ''"
            " GROUP BY feature_slug"
        ):
            by_feature[row["feature_slug"]] = row["cnt"]
        s["by_feature"] = by_feature

        row = conn.execute("SELECT COUNT(*) as cnt FROM issues").fetchone()
        s["total"] = row["cnt"] if row else 0

        return s
    finally:
        # Read-only — rollback releases the snapshot lock
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Bulk Access (for JSONL export/import)
# ---------------------------------------------------------------------------

def all_issues(conn: sqlite3.Connection) -> list[Issue]:
    rows = conn.execute(
        "SELECT * FROM issues ORDER BY id"
    ).fetchall()
    return [_row_to_issue(r) for r in rows]


def all_dependencies(conn: sqlite3.Connection) -> list[Dependency]:
    rows = conn.execute(
        "SELECT * FROM dependencies ORDER BY issue_id, depends_on_id"
    ).fetchall()
    return [
        Dependency(
            issue_id=r["issue_id"],
            depends_on_id=r["depends_on_id"],
            dep_type=r["dep_type"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def all_labels(conn: sqlite3.Connection) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT issue_id, label FROM labels ORDER BY issue_id, label"
    ).fetchall()
    result: dict[str, list[str]] = {}
    for r in rows:
        result.setdefault(r["issue_id"], []).append(r["label"])
    return result


def all_events(conn: sqlite3.Connection) -> list[Event]:
    """All events sorted by issue_id then id (for JSONL export)."""
    rows = conn.execute(
        "SELECT * FROM events ORDER BY issue_id, id"
    ).fetchall()
    return [_row_to_event(r) for r in rows]
