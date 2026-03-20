#!/usr/bin/env python3
"""cnogo Memory Engine — Public API.

Purpose-built issue tracker for cnogo's artifact-driven SDLC.
Zero external dependencies (stdlib + sqlite3 only).

Usage from commands:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path('.').resolve()))
    from scripts.memory import init, create, ready, claim, close

Usage from CLI:
    python3 .cnogo/scripts/workflow_memory.py ready
    python3 .cnogo/scripts/workflow_memory.py create --title "My task"
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from . import storage as _st
from .identity import content_hash as _content_hash
from .reconcile import reconcile_session
from .identity import generate_child_id as _child_id
from .identity import generate_id as _gen_id
from .graph import rebuild_blocked_cache as _rebuild_blocked_cache
from .models import ACTOR_ROLES, Dependency, Event, Issue
from .storage import with_retry as _with_retry

__all__ = [
    # Init
    "init", "is_initialized",
    # Issue CRUD
    "create", "show", "update", "claim", "close", "reopen", "release",
    "report_done", "verify_and_close", "takeover_task",
    # Query
    "ready", "list_issues", "stats", "get_phase", "set_phase", "stalled_tasks",
    # Dependencies
    "dep_add", "dep_remove", "blockers", "blocks",
    # Sync
    "export_jsonl", "import_jsonl", "sync",
    # Context
    "prime", "checkpoint", "history", "show_graph",
    # Worktree (parallel agent isolation)
    "merge_session", "cleanup_session", "load_session",
    "create_session", "save_session", "get_conflict_context",
    # Bridge (plan → task descriptions)
    "plan_to_task_descriptions", "generate_implement_prompt",
    "detect_file_conflicts", "generate_run_id",
    # Reconcile (compaction recovery)
    "reconcile_session",
    # Cost tracking
    "record_cost_event", "get_cost_summary", "cost_summary", "parse_transcript",
    # Health monitoring (watchdog)
    "check_stale_issues",
    # Leader reconciliation
    "reconcile",
]

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_DB_NAME = "memory.db"
_CNOGO_DIR = ".cnogo"
_root: Path | None = None
_RATIONALIZATION_PATTERNS = [
    re.compile(r"\btoo\s+small\b", re.IGNORECASE),
    re.compile(r"\btoo\s+simple\b", re.IGNORECASE),
    re.compile(r"\bskip(?:ping)?\s+tdd\b", re.IGNORECASE),
    re.compile(r"\bdo(?:n'?t| not)\s+need\s+tests?\b", re.IGNORECASE),
    re.compile(r"\balready\s+works\b", re.IGNORECASE),
    re.compile(r"\bprobably\s+fine\b", re.IGNORECASE),
    re.compile(r"\bseems?\s+fine\b", re.IGNORECASE),
    re.compile(r"\bno\s+time\b", re.IGNORECASE),
    re.compile(r"\blater\b", re.IGNORECASE),
]


def _db_path(root: Path | None = None) -> Path:
    r = root or _root or Path(".")
    return r / _CNOGO_DIR / _DB_NAME


def _conn(root: Path | None = None):  # noqa: ANN202
    """Get a connection to the memory database."""
    return _st.connect(_db_path(root))


def _emit(conn, issue_id: str, event_type: str, actor: str,
          data: dict[str, Any] | None = None) -> None:
    """Record an event in the audit trail."""
    _st.insert_event(conn, Event(
        issue_id=issue_id,
        event_type=event_type,
        actor=actor,
        data=data or {},
        created_at=_st._now(),
    ))


def _auto_export(root: Path) -> None:
    """Best-effort JSONL export after state-changing operations.

    Keeps .cnogo/issues.jsonl in sync with SQLite so git always sees
    the latest state. Failures are silently ignored — JSONL is a
    convenience layer, not the source of truth.
    """
    try:
        from .sync import export_jsonl as _export
        _export(root)
    except Exception:
        pass


def _load_enforcement_levels(root: Path) -> dict[str, str]:
    defaults = {
        "tddMode": "error",
        "verificationBeforeCompletion": "error",
        "taskOwnership": "error",
    }
    cfg_path = root / "docs" / "planning" / "WORKFLOW.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    if not isinstance(cfg, dict):
        return defaults
    enforcement = cfg.get("enforcement")
    if not isinstance(enforcement, dict):
        return defaults

    out = dict(defaults)
    tdd_mode = enforcement.get("tddMode")
    if tdd_mode in {"off", "warn", "error"}:
        out["tddMode"] = tdd_mode
    vbc = enforcement.get("verificationBeforeCompletion")
    if vbc in {"off", "warn", "error"}:
        out["verificationBeforeCompletion"] = vbc
    ownership = enforcement.get("taskOwnership")
    if ownership in {"off", "warn", "error"}:
        out["taskOwnership"] = ownership
    return out


def _load_agent_team_settings(root: Path) -> dict[str, int]:
    defaults = {
        "staleIndicatorMinutes": 10,
        "maxTakeoversPerTask": 2,
    }
    cfg_path = root / "docs" / "planning" / "WORKFLOW.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    if not isinstance(cfg, dict):
        return defaults
    teams = cfg.get("agentTeams")
    if not isinstance(teams, dict):
        return defaults

    out = dict(defaults)
    stale = teams.get("staleIndicatorMinutes")
    if isinstance(stale, int) and not isinstance(stale, bool) and stale > 0:
        out["staleIndicatorMinutes"] = stale
    max_takeovers = teams.get("maxTakeoversPerTask")
    if isinstance(max_takeovers, int) and not isinstance(max_takeovers, bool) and max_takeovers >= 0:
        out["maxTakeoversPerTask"] = max_takeovers
    return out


def _parse_iso_timestamp(value: str) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _contains_rationalization(text: str) -> bool:
    return any(p.search(text or "") for p in _RATIONALIZATION_PATTERNS)


def _is_nonempty_cmd_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(v, str) and v.strip() for v in value
    )


def _outputs_dict(metadata: dict[str, Any]) -> dict[str, Any]:
    outputs = metadata.get("outputs")
    return outputs if isinstance(outputs, dict) else {}


def _verification_evidence(outputs: dict[str, Any]) -> dict[str, Any] | None:
    verification = outputs.get("verification") or outputs.get("verificationEvidence")
    return verification if isinstance(verification, dict) else None


def _verification_timestamp(outputs: dict[str, Any]) -> str:
    verification = _verification_evidence(outputs)
    if not isinstance(verification, dict):
        return ""
    ts = verification.get("timestamp")
    return ts.strip() if isinstance(ts, str) else ""


def _completion_evidence_findings(
    issue: Issue,
    *,
    verification_level: str,
    tdd_level: str,
) -> list[tuple[str, str]]:
    """Validate completion evidence payload attached by report_done outputs."""
    findings: list[tuple[str, str]] = []
    metadata = issue.metadata if isinstance(issue.metadata, dict) else {}
    requires_evidence = bool(metadata.get("requiresCompletionEvidence"))
    if not requires_evidence and _is_nonempty_cmd_list(metadata.get("verify")):
        requires_evidence = True
    if not requires_evidence:
        return findings

    outputs_dict = _outputs_dict(metadata)

    if verification_level != "off":
        verification = _verification_evidence(outputs_dict)
        if not isinstance(verification, dict):
            findings.append((verification_level, "Missing verification evidence object in TASK_EVIDENCE."))
        else:
            commands = verification.get("commands")
            timestamp = verification.get("timestamp")
            if not _is_nonempty_cmd_list(commands):
                findings.append((verification_level, "Verification evidence must include non-empty commands[]."))
            if not isinstance(timestamp, str) or not timestamp.strip():
                findings.append((verification_level, "Verification evidence must include non-empty timestamp."))

    expected_tdd = metadata.get("tdd") if isinstance(metadata.get("tdd"), dict) else None
    has_tdd_contract = isinstance(expected_tdd, dict) and isinstance(expected_tdd.get("required"), bool)

    if tdd_level != "off" and has_tdd_contract:
        tdd = outputs_dict.get("tdd") or outputs_dict.get("tddEvidence")
        if not isinstance(tdd, dict):
            findings.append((tdd_level, "Missing TDD evidence object in TASK_EVIDENCE."))
            return findings

        required = tdd.get("required")
        if not isinstance(required, bool):
            findings.append((tdd_level, "TDD evidence must include required=true|false."))
            return findings

        expected_required = expected_tdd.get("required") if isinstance(expected_tdd, dict) else None
        if isinstance(expected_required, bool) and expected_required != required:
            findings.append((tdd_level, "TDD evidence required flag does not match plan contract."))

        if required:
            if not _is_nonempty_cmd_list(tdd.get("failingVerify")):
                findings.append((tdd_level, "TDD evidence must include non-empty failingVerify[]."))
            if not _is_nonempty_cmd_list(tdd.get("passingVerify")):
                findings.append((tdd_level, "TDD evidence must include non-empty passingVerify[]."))
        else:
            reason = tdd.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                findings.append((tdd_level, "TDD evidence with required=false must include non-empty reason."))
            elif _contains_rationalization(reason):
                findings.append((tdd_level, "TDD exemption reason appears rationalized."))

    return findings


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init(root: Path) -> None:
    """Initialize .cnogo/ directory with memory.db schema."""
    global _root
    _root = root
    cnogo_dir = root / _CNOGO_DIR
    cnogo_dir.mkdir(parents=True, exist_ok=True)
    conn = _st.connect(cnogo_dir / _DB_NAME)
    conn.close()


def is_initialized(root: Path | None = None) -> bool:
    """Check if memory engine is set up in this project."""
    r = root or _root or Path(".")
    return (r / _CNOGO_DIR / _DB_NAME).exists()


# ---------------------------------------------------------------------------
# Issue CRUD
# ---------------------------------------------------------------------------

def create(
    title: str,
    *,
    issue_type: str = "task",
    parent: str | None = None,
    feature_slug: str | None = None,
    plan_number: str | None = None,
    phase: str | None = None,
    priority: int = 2,
    labels: list[str] | None = None,
    description: str | None = None,
    metadata: dict | None = None,
    owner_actor: str = "",
    actor: str = "claude",
    root: Path | None = None,
) -> Issue:
    """Create a new issue. Returns Issue with generated ID.

    Retries on SQLITE_BUSY with exponential backoff for multi-agent
    robustness.
    """
    r = root or _root or Path(".")

    def _do_create() -> Issue:
        conn = _conn(r)
        try:
            # Acquire write lock early for child counter atomicity (W-1)
            conn.execute("BEGIN IMMEDIATE")
            now = _st._now()

            # Generate ID — hierarchical if parent given, hash-based otherwise
            if parent is not None:
                if not _st.id_exists(conn, parent):
                    raise ValueError(f"Parent issue {parent} not found")
                child_num = _st.next_child_number(conn, parent)
                issue_id = _child_id(parent, child_num)
            else:
                # Try with increasing nonce, then more bytes on collision
                issue_id = ""
                for nonce in range(10):
                    candidate = _gen_id(title, actor, nonce=nonce)
                    if not _st.id_exists(conn, candidate):
                        issue_id = candidate
                        break
                if not issue_id:
                    # Extend to 5 bytes
                    for nonce in range(10):
                        candidate = _gen_id(title, actor, id_bytes=5, nonce=nonce)
                        if not _st.id_exists(conn, candidate):
                            issue_id = candidate
                            break
                if not issue_id:
                    raise RuntimeError("Failed to generate unique ID after retries")

            chash = _content_hash(title, description or "", issue_type)

            issue = Issue(
                id=issue_id,
                title=title,
                content_hash=chash,
                description=description or "",
                status="open",
                state="open",
                issue_type=issue_type,
                priority=priority,
                assignee="",
                owner_actor=owner_actor or "",
                feature_slug=feature_slug or "",
                plan_number=plan_number or "",
                phase=_st.normalize_phase(phase or "discuss"),
                metadata=metadata or {},
                created_at=now,
                updated_at=now,
            )

            _st.insert_issue(conn, issue)

            # Labels
            for lbl in (labels or []):
                _st.add_label(conn, issue_id, lbl)
            issue.labels = labels or []

            # Parent-child dependency
            if parent is not None:
                dep = Dependency(
                    issue_id=issue_id,
                    depends_on_id=parent,
                    dep_type="parent-child",
                    created_at=now,
                )
                _st.insert_dependency(conn, dep)

            # Event
            _emit(conn, issue_id, "created", actor, {
                "title": title,
                "issue_type": issue_type,
                "parent": parent,
            })

            # Rebuild blocked cache after structural change
            _rebuild_blocked_cache(conn)

            conn.commit()
            return issue
        finally:
            conn.close()

    result = _with_retry(_do_create)
    _auto_export(r)
    return result


def show(issue_id: str, *, root: Path | None = None) -> Issue | None:
    """Get full issue details including deps, labels, and recent events."""
    conn = _conn(root)
    try:
        issue = _st.get_issue(conn, issue_id)
        if issue is None:
            return None
        issue.labels = _st.get_labels(conn, issue_id)
        issue.deps = _st.get_dependencies(conn, issue_id)
        issue.blocks_issues = [
            i.id for i in _st.get_blocks(conn, issue_id)
        ]
        issue.recent_events = _st.get_events(conn, issue_id, limit=10)
        return issue
    finally:
        conn.close()


def update(
    issue_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    assignee: str | None = None,
    metadata: dict | None = None,
    comment: str | None = None,
    actor: str = "claude",
    root: Path | None = None,
) -> Issue:
    """Update issue fields. Emits 'updated' event.

    The ``assignee`` parameter allows direct reassignment without going
    through the release/claim cycle. Pass an empty string to unassign.
    """
    r = root or _root or Path(".")
    conn = _conn(r)
    try:
        existing = _st.get_issue(conn, issue_id)
        if existing is None:
            raise ValueError(f"Issue {issue_id} not found")

        fields: dict[str, Any] = {}
        changes: dict[str, Any] = {}

        if title is not None and title != existing.title:
            fields["title"] = title
            changes["title"] = {"old": existing.title, "new": title}
        if description is not None and description != existing.description:
            fields["description"] = description
            changes["description"] = True
        if priority is not None and priority != existing.priority:
            fields["priority"] = priority
            changes["priority"] = {"old": existing.priority, "new": priority}
        if assignee is not None and assignee != existing.assignee:
            fields["assignee"] = assignee
            changes["assignee"] = {"old": existing.assignee, "new": assignee}
        if metadata is not None:
            merged = {**existing.metadata, **metadata}
            fields["metadata"] = merged
            changes["metadata_keys"] = list(metadata.keys())

        if fields:
            # Recompute content hash
            new_title = fields.get("title", existing.title)
            new_desc = fields.get("description", existing.description)
            fields["content_hash"] = _content_hash(
                new_title, new_desc, existing.issue_type
            )
            _st.update_issue_fields(conn, issue_id, **fields)

        if comment:
            _emit(conn, issue_id, "commented", actor, {"comment": comment})
        if changes:
            _emit(conn, issue_id, "updated", actor, changes)

        conn.commit()
        result = _st.get_issue(conn, issue_id)  # type: ignore[return-value]
    finally:
        conn.close()
    _auto_export(r)
    return result


def claim(
    issue_id: str,
    *,
    actor: str,
    root: Path | None = None,
) -> Issue:
    """Atomic claim: sets assignee + in_progress.

    Idempotent when the same actor already owns an in-progress task
    that is still actively in_progress.

    Retries on SQLITE_BUSY with exponential backoff for multi-agent
    robustness.
    """
    r = root or _root or Path(".")

    def _do_claim() -> Issue:
        conn = _conn(r)
        try:
            # Acquire write lock early for CAS atomicity (W-6)
            conn.execute("BEGIN IMMEDIATE")
            existing = _st.get_issue(conn, issue_id)
            if existing is None:
                raise ValueError(f"Issue {issue_id} not found")
            if existing.status == "closed":
                raise ValueError(f"Issue {issue_id} is closed")
            if existing.assignee == actor and existing.status == "in_progress":
                if existing.state == "in_progress":
                    conn.commit()
                    return existing
                raise ValueError(
                    f"Issue {issue_id} already owned by {actor!r} but state is "
                    f"{existing.state!r}; cannot re-claim"
                )

            ok = _st.claim_issue(conn, issue_id, actor)
            if not ok:
                raise ValueError(
                    f"Issue {issue_id} already claimed by {existing.assignee!r}"
                )

            _st.update_issue_fields(conn, issue_id, state="in_progress")
            _emit(conn, issue_id, "claimed", actor)
            conn.commit()
            return _st.get_issue(conn, issue_id)  # type: ignore[return-value]
        finally:
            conn.close()

    result = _with_retry(_do_claim)
    _auto_export(r)
    return result


# ---------------------------------------------------------------------------
# Two-phase completion (Contract 02, 04, 05)
# ---------------------------------------------------------------------------

def _validate_transition(
    issue: Issue,
    from_state: str,
    to_state: str,
    actor_role: str,
) -> None:
    """Validate a state transition. Raises ValueError on violation."""
    valid = issue.valid_states()
    if to_state not in valid:
        raise ValueError(
            f"Invalid target state {to_state!r} for {issue.issue_type}. "
            f"Valid: {valid}"
        )
    if from_state != issue.state:
        raise ValueError(
            f"State mismatch: expected {from_state!r}, got {issue.state!r}"
        )
    if actor_role not in ACTOR_ROLES:
        raise ValueError(
            f"Invalid actor_role {actor_role!r}. Valid: {sorted(ACTOR_ROLES)}"
        )


def report_done(
    issue_id: str,
    *,
    outputs: dict | None = None,
    actor: str,
    actor_role: str = "worker",
    root: Path | None = None,
) -> Issue:
    """Worker reports task completion. Sets state to 'done_by_worker'.

    Only workers and hooks can call this. Only tasks can be reported done.
    """
    if actor_role not in ("worker", "hook"):
        raise ValueError(
            f"Only worker or hook can report_done, got {actor_role!r}"
        )

    r = root or _root or Path(".")
    enforcement = _load_enforcement_levels(r)
    ownership_level = enforcement.get("taskOwnership", "error")

    def _do_report() -> Issue:
        conn = _conn(r)
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = _st.get_issue(conn, issue_id)
            if existing is None:
                raise ValueError(f"Issue {issue_id} not found")
            if existing.issue_type != "task":
                raise ValueError(
                    f"report_done only works on tasks, got {existing.issue_type!r}"
                )
            policy_warnings: list[str] = []
            if not existing.assignee:
                message = "Cannot report_done without an assignee (unclaimed task)."
                if ownership_level == "error":
                    raise ValueError(message)
                if ownership_level == "warn":
                    policy_warnings.append(message)
            elif existing.assignee != actor:
                message = (
                    "report_done actor must match assignee under taskOwnership policy "
                    f"(assignee={existing.assignee!r}, actor={actor!r})."
                )
                if ownership_level == "error":
                    raise ValueError(message)
                if ownership_level == "warn":
                    policy_warnings.append(message)
            if existing.state not in {"in_progress", "done_by_worker"}:
                raise ValueError(
                    "report_done requires task state in_progress|done_by_worker, "
                    f"got {existing.state!r}"
                )
            if actor_role == "hook":
                if not existing.owner_actor or existing.owner_actor != actor:
                    raise ValueError(
                        "Hook can only report_done for owned tasks"
                    )

            _validate_transition(existing, existing.state, "done_by_worker", actor_role)
            _st.update_issue_fields(conn, issue_id, state="done_by_worker")

            if outputs:
                merged_meta = {**existing.metadata, "outputs": outputs}
                _st.update_issue_fields(conn, issue_id, metadata=merged_meta)

            _emit(conn, issue_id, "report_done", actor, {
                "actor_role": actor_role,
                "outputs": outputs or {},
                "policy_warnings": policy_warnings,
            })
            conn.commit()
            return _st.get_issue(conn, issue_id)  # type: ignore[return-value]
        finally:
            conn.close()

    result = _with_retry(_do_report)
    _auto_export(r)
    return result


def verify_and_close(
    issue_id: str,
    *,
    reason: str = "completed",
    comment: str | None = None,
    actor: str = "claude",
    root: Path | None = None,
) -> Issue:
    """Leader verifies and closes a task. Two-phase: done_by_worker -> verified -> closed.

    This function is leader-only by design.
    """
    r = root or _root or Path(".")
    enforcement = _load_enforcement_levels(r)
    verification_level = enforcement.get("verificationBeforeCompletion", "error")
    tdd_level = enforcement.get("tddMode", "error")

    def _do_verify() -> Issue:
        conn = _conn(r)
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = _st.get_issue(conn, issue_id)
            if existing is None:
                raise ValueError(f"Issue {issue_id} not found")
            if existing.issue_type != "task":
                raise ValueError(
                    f"verify_and_close only works on tasks, got {existing.issue_type!r}"
                )

            evidence_findings = _completion_evidence_findings(
                existing,
                verification_level=verification_level,
                tdd_level=tdd_level,
            )
            blocking = [msg for level, msg in evidence_findings if level == "error"]
            if blocking:
                joined = "; ".join(blocking)
                raise ValueError(
                    "Completion evidence policy violation: "
                    f"{joined}"
                )

            if existing.state == "done_by_worker":
                # Phase 1: done_by_worker -> verified
                _st.update_issue_fields(conn, issue_id, state="verified")
                _emit(conn, issue_id, "verified", actor)
                # Phase 2: verified -> closed
                _st.update_issue_fields(conn, issue_id, state="closed")
                _st.close_issue(conn, issue_id, reason)
                _emit(conn, issue_id, "closed", actor, {
                    "reason": reason,
                    "comment": comment or "",
                })
            elif existing.state == "verified":
                # Already verified, just close
                _st.update_issue_fields(conn, issue_id, state="closed")
                _st.close_issue(conn, issue_id, reason)
                _emit(conn, issue_id, "closed", actor, {
                    "reason": reason,
                    "comment": comment or "",
                })
            else:
                raise ValueError(
                    f"Cannot verify task in state {existing.state!r}"
                )

            _rebuild_blocked_cache(conn)
            conn.commit()
            return _st.get_issue(conn, issue_id)  # type: ignore[return-value]
        finally:
            conn.close()

    result = _with_retry(_do_verify)
    _auto_export(r)
    return result


def close(
    issue_id: str,
    *,
    reason: str = "completed",
    comment: str | None = None,
    actor: str = "claude",
    actor_role: str = "leader",
    root: Path | None = None,
) -> Issue:
    """Close an issue. Rebuilds blocked cache and auto-exports JSONL.

    Role enforcement (Contract 04):
    - Only leader can close plan/epic issues.
    - Workers should use report_done() for task completion.

    Retries on SQLITE_BUSY with exponential backoff for multi-agent
    robustness.
    """
    r = root or _root or Path(".")
    existing_issue = show(issue_id, root=r)
    if existing_issue and actor_role == "leader" and existing_issue.issue_type == "task":
        return verify_and_close(
            issue_id,
            reason=reason,
            comment=comment,
            actor=actor,
            root=r,
        )

    def _do_close() -> Issue:
        conn = _conn(r)
        try:
            existing = _st.get_issue(conn, issue_id)
            if existing is None:
                raise ValueError(f"Issue {issue_id} not found")

            # Role enforcement (Contract 04)
            if actor_role != "leader" and existing.issue_type in ("plan", "epic"):
                raise ValueError(
                    f"Only leader can close {existing.issue_type} issues"
                )
            if actor_role != "leader" and existing.issue_type == "task":
                raise ValueError(
                    "Use report_done() for worker task completion"
                )

            ok = _st.close_issue(conn, issue_id, reason)
            if not ok:
                raise ValueError(f"Issue {issue_id} is already closed")

            _st.update_issue_fields(conn, issue_id, state="closed")
            _emit(conn, issue_id, "closed", actor, {
                "reason": reason,
                "comment": comment or "",
            })

            _rebuild_blocked_cache(conn)
            conn.commit()
            return _st.get_issue(conn, issue_id)  # type: ignore[return-value]
        finally:
            conn.close()

    result = _with_retry(_do_close)
    _auto_export(r)
    return result


def reopen(
    issue_id: str,
    *,
    actor: str = "claude",
    root: Path | None = None,
) -> Issue:
    """Reopen a closed issue."""
    r = root or _root or Path(".")
    conn = _conn(r)
    try:
        existing = _st.get_issue(conn, issue_id)
        if existing is None:
            raise ValueError(f"Issue {issue_id} not found")

        ok = _st.reopen_issue(conn, issue_id)
        if not ok:
            raise ValueError(f"Issue {issue_id} is not closed")

        _emit(conn, issue_id, "reopened", actor)
        _rebuild_blocked_cache(conn)
        conn.commit()
        result = _st.get_issue(conn, issue_id)  # type: ignore[return-value]
    finally:
        conn.close()
    _auto_export(r)
    return result


def release(
    issue_id: str,
    *,
    actor: str = "claude",
    actor_role: str = "leader",
    root: Path | None = None,
) -> Issue:
    """Release a claimed (in_progress) issue back to open/unassigned.

    Used to reclaim tasks from dead agents or re-assign work.
    Only valid for actively executing tasks (state=in_progress).
    Resets status to 'open' and clears assignee.
    """
    if actor_role != "leader":
        raise ValueError("Only leader can release in-progress issues")
    r = root or _root or Path(".")
    conn = _conn(r)
    try:
        existing = _st.get_issue(conn, issue_id)
        if existing is None:
            raise ValueError(f"Issue {issue_id} not found")
        if existing.issue_type != "task":
            raise ValueError(
                f"release only works on tasks, got {existing.issue_type!r}"
            )
        if existing.state != "in_progress":
            raise ValueError(
                "release requires task in active execution state "
                f"(state='in_progress'), got state={existing.state!r}"
            )

        ok = _st.release_issue(conn, issue_id)
        if not ok:
            raise ValueError(
                f"Issue {issue_id} is not in_progress (status={existing.status!r})"
            )

        _emit(conn, issue_id, "released", actor, {
            "previous_assignee": existing.assignee,
        })
        _rebuild_blocked_cache(conn)
        conn.commit()
        result = _st.get_issue(conn, issue_id)  # type: ignore[return-value]
    finally:
        conn.close()
    _auto_export(r)
    return result


def takeover_task(
    issue_id: str,
    *,
    to_actor: str,
    reason: str,
    actor: str = "leader",
    actor_role: str = "leader",
    root: Path | None = None,
) -> dict[str, Any]:
    """Leader-only takeover of a stalled task.

    Reassigns assignee, moves task back to in_progress, and records audit data.
    """
    if actor_role != "leader":
        raise ValueError("Only leader can run takeover_task")
    to_actor_clean = (to_actor or "").strip()
    if not to_actor_clean:
        raise ValueError("takeover target actor cannot be empty")
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise ValueError("takeover reason cannot be empty")

    r = root or _root or Path(".")
    max_takeovers = _load_agent_team_settings(r).get("maxTakeoversPerTask", 2)

    def _do_takeover() -> dict[str, Any]:
        conn = _conn(r)
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = _st.get_issue(conn, issue_id)
            if existing is None:
                raise ValueError(f"Issue {issue_id} not found")
            if existing.issue_type != "task":
                raise ValueError(
                    f"takeover_task only works on tasks, got {existing.issue_type!r}"
                )
            if existing.status == "closed" or existing.state == "closed":
                raise ValueError(f"Issue {issue_id} is closed")
            if existing.status != "in_progress" or existing.state != "in_progress":
                raise ValueError(
                    "takeover_task requires task in active execution state "
                    f"(status='in_progress', state='in_progress'), got "
                    f"(status={existing.status!r}, state={existing.state!r})"
                )

            row = conn.execute(
                "SELECT COUNT(1) AS c FROM events WHERE issue_id = ? AND event_type = 'taken_over'",
                (issue_id,),
            ).fetchone()
            attempts_so_far = int(row["c"] or 0) if row else 0
            if attempts_so_far >= max_takeovers:
                raise ValueError(
                    f"Takeover limit reached for {issue_id}: {attempts_so_far}/{max_takeovers}"
                )

            from_actor = existing.assignee or ""
            if from_actor == to_actor_clean and existing.state == "in_progress":
                return {
                    "id": issue_id,
                    "from_actor": from_actor,
                    "to_actor": to_actor_clean,
                    "attempt": attempts_so_far,
                    "max_attempts": max_takeovers,
                    "state": existing.state,
                    "status": existing.status,
                    "idempotent": True,
                }

            _st.update_issue_fields(
                conn,
                issue_id,
                assignee=to_actor_clean,
                status="in_progress",
                state="in_progress",
            )
            attempt = attempts_so_far + 1
            _emit(conn, issue_id, "taken_over", actor, {
                "from_actor": from_actor,
                "to_actor": to_actor_clean,
                "reason": reason_clean,
                "attempt": attempt,
                "max_attempts": max_takeovers,
            })
            _rebuild_blocked_cache(conn)
            conn.commit()

            fresh = _st.get_issue(conn, issue_id)
            return {
                "id": issue_id,
                "from_actor": from_actor,
                "to_actor": to_actor_clean,
                "attempt": attempt,
                "max_attempts": max_takeovers,
                "state": fresh.state if fresh else "in_progress",
                "status": fresh.status if fresh else "in_progress",
                "idempotent": False,
            }
        finally:
            conn.close()

    result = _with_retry(_do_takeover)
    _auto_export(r)
    return result


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def ready(
    *,
    assignee: str | None = None,
    feature_slug: str | None = None,
    label: str | None = None,
    limit: int = 20,
    root: Path | None = None,
) -> list[Issue]:
    """Get unblocked, open issues ready for work."""
    conn = _conn(root)
    try:
        return _st.ready_issues_query(
            conn,
            assignee=assignee,
            feature_slug=feature_slug,
            label=label,
            limit=limit,
        )
    finally:
        conn.close()


def stalled_tasks(
    *,
    feature_slug: str | None = None,
    stale_minutes: int | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return in-progress tasks older than stale threshold."""
    r = root or _root or Path(".")
    configured_stale = _load_agent_team_settings(r).get("staleIndicatorMinutes", 10)
    threshold = stale_minutes if isinstance(stale_minutes, int) and stale_minutes > 0 else configured_stale

    now = datetime.now(timezone.utc)
    issues = list_issues(
        status="in_progress",
        issue_type="task",
        feature_slug=feature_slug,
        limit=1000,
        root=r,
    )
    stale: list[dict[str, Any]] = []
    for issue in issues:
        if issue.state != "in_progress":
            continue
        updated = _parse_iso_timestamp(issue.updated_at)
        if updated is None:
            continue
        age_minutes = (now - updated).total_seconds() / 60.0
        if age_minutes < float(threshold):
            continue
        stale.append({
            "id": issue.id,
            "title": issue.title,
            "assignee": issue.assignee,
            "feature": issue.feature_slug,
            "planNumber": issue.plan_number,
            "status": issue.status,
            "state": issue.state,
            "updatedAt": issue.updated_at,
            "minutesStale": round(age_minutes, 1),
        })
    stale.sort(key=lambda item: float(item["minutesStale"]), reverse=True)
    return stale


def list_issues(
    *,
    status: str | None = None,
    issue_type: str | None = None,
    feature_slug: str | None = None,
    parent: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    limit: int = 100,
    root: Path | None = None,
) -> list[Issue]:
    """List issues with optional filters."""
    conn = _conn(root)
    try:
        return _st.list_issues_query(
            conn,
            status=status,
            issue_type=issue_type,
            feature_slug=feature_slug,
            parent=parent,
            assignee=assignee,
            label=label,
            limit=limit,
        )
    finally:
        conn.close()


def stats(*, root: Path | None = None) -> dict:
    """Return counts: open, in_progress, closed, ready, blocked, by_type, by_feature."""
    conn = _conn(root)
    try:
        return _st.get_stats(conn)
    finally:
        conn.close()


def get_phase(
    feature_slug: str,
    *,
    root: Path | None = None,
) -> str:
    """Get current workflow phase for a feature."""
    conn = _conn(root)
    try:
        return _st.get_feature_phase(conn, feature_slug)
    finally:
        conn.close()


def set_phase(
    feature_slug: str,
    phase: str,
    *,
    root: Path | None = None,
) -> int:
    """Set workflow phase for all issues in a feature.

    Returns number of updated rows.
    """
    r = root or _root or Path(".")
    def _do_set() -> int:
        conn = _conn(r)
        try:
            conn.execute("BEGIN IMMEDIATE")
            count = _st.set_feature_phase(conn, feature_slug, phase)
            conn.commit()
            return count
        finally:
            conn.close()

    count = _with_retry(_do_set)
    _auto_export(r)
    return count


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def dep_add(
    issue_id: str,
    depends_on: str,
    *,
    dep_type: str = "blocks",
    actor: str = "claude",
    root: Path | None = None,
) -> None:
    """Add dependency. Raises on cycle detection."""
    r = root or _root or Path(".")
    conn = _conn(r)
    try:
        # Validate both issues exist
        if not _st.id_exists(conn, issue_id):
            raise ValueError(f"Issue {issue_id} not found")
        if not _st.id_exists(conn, depends_on):
            raise ValueError(f"Issue {depends_on} not found")

        # Cycle detection
        if _would_create_cycle(conn, issue_id, depends_on):
            raise ValueError(
                f"Adding {issue_id} → {depends_on} would create a cycle"
            )

        dep = Dependency(
            issue_id=issue_id,
            depends_on_id=depends_on,
            dep_type=dep_type,
            created_at=_st._now(),
        )
        _st.insert_dependency(conn, dep)

        _emit(conn, issue_id, "dep_added", actor, {
            "depends_on": depends_on,
            "dep_type": dep_type,
        })

        _rebuild_blocked_cache(conn)
        conn.commit()
    finally:
        conn.close()
    _auto_export(r)


def dep_remove(
    issue_id: str,
    depends_on: str,
    *,
    actor: str = "claude",
    root: Path | None = None,
) -> None:
    """Remove dependency. Rebuilds blocked cache."""
    r = root or _root or Path(".")
    conn = _conn(r)
    try:
        ok = _st.remove_dependency(conn, issue_id, depends_on)
        if ok:
            _emit(conn, issue_id, "dep_removed", actor, {
                "depends_on": depends_on,
            })
            _rebuild_blocked_cache(conn)
        conn.commit()
    finally:
        conn.close()
    _auto_export(r)


def blockers(
    issue_id: str,
    *,
    root: Path | None = None,
) -> list[Issue]:
    """Get issues blocking this one."""
    conn = _conn(root)
    try:
        return _st.get_blocked_by(conn, issue_id)
    finally:
        conn.close()


def blocks(
    issue_id: str,
    *,
    root: Path | None = None,
) -> list[Issue]:
    """Get issues this one blocks."""
    conn = _conn(root)
    try:
        return _st.get_blocks(conn, issue_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Blocked Cache & Cycle Detection
# ---------------------------------------------------------------------------

_CYCLE_MAX_ITERATIONS = 10_000


def _would_create_cycle(conn, issue_id: str, depends_on_id: str) -> bool:
    """Check if adding issue_id -> depends_on_id would create a cycle.

    DFS from depends_on_id following outgoing edges. If we reach issue_id,
    a cycle would form. Bounded to _CYCLE_MAX_ITERATIONS to prevent DoS
    on pathologically large graphs.
    """
    visited: set[str] = set()
    stack = [depends_on_id]
    iterations = 0
    while stack:
        iterations += 1
        if iterations > _CYCLE_MAX_ITERATIONS:
            raise ValueError(
                f"Cycle detection exceeded {_CYCLE_MAX_ITERATIONS} iterations"
            )
        current = stack.pop()
        if current == issue_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        rows = conn.execute(
            "SELECT depends_on_id FROM dependencies WHERE issue_id = ?",
            (current,),
        ).fetchall()
        for row in rows:
            stack.append(row["depends_on_id"])
    return False


# ---------------------------------------------------------------------------
# Sync & Context
# ---------------------------------------------------------------------------

def export_jsonl(root: Path) -> Path:
    """Export SQLite -> .cnogo/issues.jsonl. Returns path."""
    from .sync import export_jsonl as _export
    return _export(root)


def import_jsonl(root: Path) -> int:
    """Import .cnogo/issues.jsonl -> SQLite. Returns count imported."""
    from .sync import import_jsonl as _import
    return _import(root)


def sync(root: Path) -> None:
    """Full sync: export, git add, commit if changes."""
    from .sync import sync as _sync
    _sync(root)


def prime(
    *,
    limit: int = 10,
    verbose: bool = False,
    root: Path | None = None,
) -> str:
    """Generate minimal context summary for agent injection."""
    from .context import prime as _prime
    return _prime(limit=limit, verbose=verbose, root=root)


def checkpoint(
    *,
    feature_slug: str | None = None,
    limit: int = 3,
    root: Path | None = None,
) -> str:
    """Generate a compact progress checkpoint."""
    from .context import checkpoint as _checkpoint
    return _checkpoint(feature_slug=feature_slug, limit=limit, root=root)


def history(
    issue_id: str,
    *,
    limit: int = 10,
    root: Path | None = None,
) -> str:
    """Render event history for an issue."""
    from .context import history as _history
    return _history(issue_id, limit=limit, root=root)


def show_graph(feature_slug: str, *, root: Path | None = None) -> str:
    """Render ASCII dependency graph for a feature."""
    from .context import show_graph as _show_graph
    return _show_graph(feature_slug, root=root)


# ---------------------------------------------------------------------------
# Worktree (parallel agent isolation)
# ---------------------------------------------------------------------------

def merge_session(session: Any, root: Path) -> Any:
    """Merge agent branches sequentially in task order."""
    from .worktree import merge_session as _merge
    return _merge(session, root)


def cleanup_session(session: Any, root: Path) -> None:
    """Remove all worktrees, delete branches, and remove state file."""
    from .worktree import cleanup_session as _cleanup
    _cleanup(session, root)


def load_session(root: Path) -> Any:
    """Read and deserialize worktree session state. Returns None if no file."""
    from .worktree import load_session as _load
    return _load(root)


def create_session(
    plan_json_path: Path,
    root: Path,
    task_descriptions: list[dict[str, Any]],
    *,
    run_id: str = "",
) -> Any:
    """Create worktrees for parallel agent execution. Requires TaskDesc V2."""
    from .worktree import create_session as _create
    return _create(plan_json_path, root, task_descriptions, run_id=run_id)


def save_session(session: Any, root: Path) -> None:
    """Serialize session to JSON, write atomically."""
    from .worktree import save_session as _save
    _save(session, root)


def get_conflict_context(
    session: Any,
    task_index: int,
    plan_json_path: Path,
    root: Path,
) -> dict[str, Any]:
    """Build context dict for the resolver agent."""
    from .worktree import get_conflict_context as _get
    return _get(session, task_index, plan_json_path, root)


# ---------------------------------------------------------------------------
# Bridge (plan → task descriptions)
# ---------------------------------------------------------------------------


def plan_to_task_descriptions(
    plan_json_path: Path,
    root: Path,
) -> list[dict[str, Any]]:
    """Read plan JSON and generate TaskDesc V2 objects."""
    from .bridge import plan_to_task_descriptions as _ptd
    return _ptd(plan_json_path, root)


def generate_implement_prompt(
    taskdesc: dict[str, Any],
    *,
    actor_name: str = "implementer",
) -> str:
    """Render a TaskDesc V2 dict into a markdown agent prompt."""
    from .bridge import generate_implement_prompt as _gip
    return _gip(taskdesc, actor_name=actor_name)


def detect_file_conflicts(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check for file overlaps across tasks (advisory)."""
    from .bridge import detect_file_conflicts as _dfc
    return _dfc(tasks)


def generate_run_id(feature: str) -> str:
    """Generate a unique run ID for a team execution session."""
    from .bridge import generate_run_id as _gri
    return _gri(feature)


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

def record_cost_event(
    issue_id: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_tokens: int = 0,
    model: str = "",
    cost_usd: float = 0.0,
    actor: str = "claude",
    root: Path | None = None,
) -> None:
    """Record a cost_report event for an issue."""
    r = root or _root or Path(".")
    conn = _conn(r)
    try:
        _emit(conn, issue_id, "cost_report", actor, {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_tokens": cache_tokens,
            "model": model,
            "cost_usd": cost_usd,
        })
        conn.commit()
    finally:
        conn.close()


def get_cost_summary(feature_slug: str, *, root: Path | None = None) -> dict:
    """Aggregate cost_report events for all issues in a feature.

    Returns total_tokens, total_cost_usd, and event_count.
    """
    conn = _conn(root)
    try:
        rows = conn.execute(
            """SELECT e.data FROM events e
               JOIN issues i ON i.id = e.issue_id
               WHERE e.event_type = 'cost_report'
               AND i.feature_slug = ?""",
            (feature_slug,),
        ).fetchall()
    finally:
        conn.close()

    total_tokens = 0
    total_cost_usd = 0.0
    for row in rows:
        try:
            data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        except (json.JSONDecodeError, TypeError):
            data = {}
        total_tokens += data.get("input_tokens", 0) + data.get("output_tokens", 0)
        total_cost_usd += data.get("cost_usd", 0.0)

    return {
        "feature_slug": feature_slug,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "event_count": len(rows),
    }


def cost_summary(project_slug: str = "") -> dict:
    """Summarize costs for a project from Claude Code transcripts."""
    from .costs import summarize_project_costs as _summarize
    return _summarize(project_slug)


def parse_transcript(path: Path) -> Any:
    """Parse a single Claude Code session transcript for usage data."""
    from .costs import parse_transcript as _parse
    return _parse(path)


# ---------------------------------------------------------------------------
# Health monitoring (watchdog)
# ---------------------------------------------------------------------------

def check_stale_issues(root: Path, stale_days: int = 30) -> list:
    """Check for stale open issues with no assignee."""
    from .watchdog import check_stale_issues as _check
    return _check(root, stale_days)


# ---------------------------------------------------------------------------
# Leader reconciliation
# ---------------------------------------------------------------------------

def reconcile(
    epic_id: str,
    *,
    actor: str = "leader",
    root: Path | None = None,
) -> dict[str, Any]:
    """Run deterministic leader reconciliation for an epic."""
    from .reconcile_leader import reconcile as _reconcile
    return _reconcile(epic_id, actor=actor, root=root)
