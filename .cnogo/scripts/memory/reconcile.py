#!/usr/bin/env python3
"""Compaction recovery reconcile module.

Reconciles worktree session state after a context compaction event by
closing memory issues for worktrees that have been merged or cleaned.
Reads session state from the worktree session file or from a compaction
checkpoint, then closes the corresponding memory issues.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .worktree import load_session, WorktreeSession, WorktreeInfo

_SESSION_FILE = ".cnogo/worktree-session.json"
_CHECKPOINT_FILE = ".cnogo/compaction-checkpoint.json"

_DONE_STATUSES = frozenset({"merged", "cleaned"})


def _load_session_or_checkpoint(root: Path) -> WorktreeSession | None:
    """Load session from session file, falling back to compaction checkpoint."""
    session = load_session(root)
    if session is not None:
        return session

    checkpoint_path = root / _CHECKPOINT_FILE
    if not checkpoint_path.exists():
        return None

    try:
        data = json.loads(checkpoint_path.read_text())
        session_data = data.get("session")
        if session_data is None:
            return None
        return WorktreeSession.from_dict(session_data)
    except Exception:
        return None


def _branch_is_merged(branch: str, base_branch: str, root: Path) -> bool:
    """Return True if branch is an ancestor of base_branch (i.e. merged)."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", branch, base_branch],
            cwd=str(root),
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def reconcile_session(root: Path) -> dict:
    """Reconcile worktree session state after compaction recovery.

    Loads session state and closes memory issues for worktrees that have
    been merged or cleaned, or whose branches have been merged into the
    base branch.

    Returns a summary dict with keys:
      - reconciled: list of {id, action, status}
      - skipped: list of {id, reason}
      - errors: list of {id, error}
    """
    summary: dict = {"reconciled": [], "skipped": [], "errors": []}

    try:
        session = _load_session_or_checkpoint(root)
    except Exception:
        return summary

    if session is None:
        return summary

    # Late import to avoid circular imports
    try:
        from . import close, show, is_initialized
    except Exception:
        return summary

    if not is_initialized(root):
        return summary

    for wt in session.worktrees:
        if not wt.memory_id:
            continue

        issue_id = wt.memory_id

        if wt.status in _DONE_STATUSES:
            # Worktree is done — close the memory issue
            try:
                close(
                    issue_id,
                    reason="completed",
                    actor="session-reconcile",
                    root=root,
                )
                summary["reconciled"].append(
                    {"id": issue_id, "action": "closed", "status": wt.status}
                )
            except ValueError as e:
                err_str = str(e)
                if "already closed" in err_str.lower():
                    summary["skipped"].append(
                        {"id": issue_id, "reason": "already closed"}
                    )
                else:
                    summary["errors"].append({"id": issue_id, "error": err_str})
            except Exception as e:
                summary["errors"].append({"id": issue_id, "error": str(e)})
        else:
            # Worktree not in done status — check if branch was merged via git
            if not wt.branch or not session.base_branch:
                continue

            try:
                merged = _branch_is_merged(wt.branch, session.base_branch, root)
            except Exception as e:
                summary["errors"].append({"id": issue_id, "error": str(e)})
                continue

            if not merged:
                continue

            try:
                close(
                    issue_id,
                    reason="completed",
                    actor="session-reconcile",
                    root=root,
                )
                summary["reconciled"].append(
                    {"id": issue_id, "action": "closed", "status": wt.status}
                )
            except ValueError as e:
                err_str = str(e)
                if "already closed" in err_str.lower():
                    summary["skipped"].append(
                        {"id": issue_id, "reason": "already closed"}
                    )
                else:
                    summary["errors"].append({"id": issue_id, "error": err_str})
            except Exception as e:
                summary["errors"].append({"id": issue_id, "error": str(e)})

    return summary
