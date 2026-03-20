#!/usr/bin/env python3
"""Git worktree lifecycle primitives for multi-agent parallel execution.

Each agent gets an isolated worktree and branch. Merge conflicts are
resolved by a dedicated resolver agent. A state file enables crash
recovery at any phase.

Python stdlib only — subprocess.run for git operations.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SESSION_FILE = ".cnogo/worktree-session.json"
_CNOGO_DIR = ".cnogo"
_BRANCH_PREFIX = "agent/"

_VALID_WORKTREE_STATUSES = frozenset(
    {"created", "executing", "completed", "merged", "conflict", "cleaned"}
)

_VALID_PHASES = frozenset(
    {
        "setup",
        "executing",
        "merging",
        "merged",
        "verified",
        "cleaned",
    }
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WorktreeInfo:
    """State for a single agent worktree."""

    task_index: int
    name: str
    branch: str
    path: str  # absolute path
    status: str = "created"
    memory_id: str = ""
    conflict_files: list[str] = field(default_factory=list)
    resolved_tier: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "taskIndex": self.task_index,
            "name": self.name,
            "branch": self.branch,
            "path": self.path,
            "status": self.status,
        }
        if self.memory_id:
            d["memoryId"] = self.memory_id
        if self.conflict_files:
            d["conflictFiles"] = self.conflict_files
        else:
            d["conflictFiles"] = []
        d["resolvedTier"] = self.resolved_tier
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorktreeInfo:
        return cls(
            task_index=d["taskIndex"],
            name=d["name"],
            branch=d["branch"],
            path=d["path"],
            status=d.get("status", "created"),
            memory_id=d.get("memoryId", ""),
            conflict_files=d.get("conflictFiles", []),
            resolved_tier=d.get("resolvedTier", ""),
        )


@dataclass
class MergeResult:
    """Outcome of a merge_session() call."""

    success: bool
    merged_indices: list[int] = field(default_factory=list)
    conflict_index: int | None = None
    conflict_files: list[str] = field(default_factory=list)
    resolved_tier: str = ""


@dataclass
class WorktreeSession:
    """Full worktree session state, checkpointed to disk."""

    schema_version: int = 1
    feature: str = ""
    plan_number: str = ""
    run_id: str = ""
    base_commit: str = ""
    base_branch: str = ""
    phase: str = "setup"
    worktrees: list[WorktreeInfo] = field(default_factory=list)
    merge_order: list[int] = field(default_factory=list)
    merged_so_far: list[int] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "feature": self.feature,
            "planNumber": self.plan_number,
            "runId": self.run_id,
            "baseCommit": self.base_commit,
            "baseBranch": self.base_branch,
            "phase": self.phase,
            "worktrees": [w.to_dict() for w in self.worktrees],
            "mergeOrder": self.merge_order,
            "mergedSoFar": self.merged_so_far,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorktreeSession:
        return cls(
            schema_version=d.get("schemaVersion", 1),
            feature=d.get("feature", ""),
            plan_number=d.get("planNumber", ""),
            run_id=d.get("runId", ""),
            base_commit=d.get("baseCommit", ""),
            base_branch=d.get("baseBranch", ""),
            phase=d.get("phase", "setup"),
            worktrees=[
                WorktreeInfo.from_dict(w) for w in d.get("worktrees", [])
            ],
            merge_order=d.get("mergeOrder", []),
            merged_so_far=d.get("mergedSoFar", []),
            timestamp=d.get("timestamp", ""),
        )


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a git command, raising on non-zero exit."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )


def _current_commit(root: Path) -> str:
    """Get HEAD commit hash."""
    result = _run_git("rev-parse", "HEAD", cwd=root)
    return result.stdout.strip()


def _current_branch(root: Path) -> str:
    """Get current branch name."""
    result = _run_git("branch", "--show-current", cwd=root)
    return result.stdout.strip()


def _branch_ahead_count(root: Path, base_commit: str, branch: str) -> int:
    """Return number of commits in branch that are ahead of base_commit."""
    result = _run_git("rev-list", "--count", f"{base_commit}..{branch}", cwd=root)
    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        return 0


def _now() -> str:
    """UTC ISO-8601 timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# State file I/O
# ---------------------------------------------------------------------------


def save_session(session: WorktreeSession, root: Path) -> None:
    """Serialize session to JSON, write atomically (temp file + rename)."""
    session.timestamp = _now()
    session_path = root / _SESSION_FILE
    session_path.parent.mkdir(parents=True, exist_ok=True)

    data = json.dumps(session.to_dict(), indent=2, sort_keys=True) + "\n"

    # Atomic write: write to temp file in same directory, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(session_path.parent), suffix=".tmp"
    )
    try:
        os.write(fd, data.encode())
        os.close(fd)
        os.replace(tmp_path, str(session_path))
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass  # Already closed
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def load_session(root: Path) -> WorktreeSession | None:
    """Read and deserialize session state. Returns None if no file."""
    session_path = root / _SESSION_FILE
    if not session_path.exists():
        return None
    data = json.loads(session_path.read_text())
    return WorktreeSession.from_dict(data)


def delete_session_file(root: Path) -> None:
    """Remove the session state file."""
    session_path = root / _SESSION_FILE
    if session_path.exists():
        session_path.unlink()


# ---------------------------------------------------------------------------
# create_session — Setup Primitives
# ---------------------------------------------------------------------------


def create_session(
    plan_json_path: Path,
    root: Path,
    task_descriptions: list[dict[str, Any]],
    *,
    run_id: str = "",
) -> WorktreeSession:
    """Create worktrees for parallel agent execution.

    1. Read plan JSON for feature + planNumber
    2. Record base commit/branch
    3. For each non-skipped task: create branch, worktree, symlink .cnogo/
    4. Write session state file

    Requires TaskDesc V2 dicts (task_id, title, file_scope).
    Raises ValueError if V1-only fields are detected without V2 equivalents.

    On failure, cleans up all worktrees created so far.
    """
    # Read plan metadata
    plan_data = json.loads(plan_json_path.read_text())
    feature = plan_data["feature"]
    plan_number = plan_data["planNumber"]

    # Record base state
    base_commit = _current_commit(root)
    base_branch = _current_branch(root)

    # Project name for worktree directory naming
    project_name = root.resolve().name

    session = WorktreeSession(
        feature=feature,
        plan_number=plan_number,
        run_id=run_id,
        base_commit=base_commit,
        base_branch=base_branch,
        phase="setup",
    )

    cnogo_abs = (root / _CNOGO_DIR).resolve()
    created_worktrees: list[WorktreeInfo] = []

    try:
        for i, desc in enumerate(task_descriptions):
            if desc.get("skipped"):
                continue

            # V2 required — fail fast on V1-only input
            if "title" not in desc and "name" in desc:
                raise ValueError(
                    f"Task {i} has V1 field 'name' but no V2 'title'. "
                    "Pass TaskDesc V2 dicts from plan_to_task_descriptions()."
                )
            task_name = desc.get("title", f"task-{i}")
            memory_id = desc.get("task_id", "")

            branch_name = f"{_BRANCH_PREFIX}{feature}-{plan_number}-task-{i}"
            wt_dir = f"{project_name}-wt-{feature}-{plan_number}-{i}"
            wt_path = (root / ".." / wt_dir).resolve()

            # Create branch at base commit
            _run_git("branch", branch_name, base_commit, cwd=root)

            # Create worktree
            _run_git("worktree", "add", str(wt_path), branch_name, cwd=root)

            # Symlink .cnogo/ so agents share the same memory DB
            wt_cnogo = wt_path / _CNOGO_DIR
            if not wt_cnogo.exists():
                os.symlink(str(cnogo_abs), str(wt_cnogo))

            wt_info = WorktreeInfo(
                task_index=i,
                name=task_name,
                branch=branch_name,
                path=str(wt_path),
                status="created",
                memory_id=memory_id,
            )
            created_worktrees.append(wt_info)

        session.worktrees = created_worktrees
        session.merge_order = [w.task_index for w in created_worktrees]
        session.merged_so_far = []

        # Checkpoint: setup complete
        save_session(session, root)

        # Transition to executing
        for wt in session.worktrees:
            wt.status = "executing"
        session.phase = "executing"
        save_session(session, root)

        return session

    except Exception:
        # Rollback: remove any worktrees and branches created so far
        for wt in reversed(created_worktrees):
            try:
                _run_git(
                    "worktree", "remove", "--force", wt.path, cwd=root
                )
            except subprocess.CalledProcessError:
                pass
            try:
                _run_git("branch", "-D", wt.branch, cwd=root)
            except subprocess.CalledProcessError:
                pass
        delete_session_file(root)
        raise


# ---------------------------------------------------------------------------
# Tier 2 Auto-Resolve Helpers
# ---------------------------------------------------------------------------


def _auto_resolve_keep_incoming(root: Path, conflict_files: list[str]) -> bool:
    """Parse git conflict markers and keep only the INCOMING side.

    For each conflicted file, replaces the full conflict block with only
    the content between ======= and >>>>>>> (the incoming/agent changes).
    Stages each resolved file with `git add`. Returns True if all files
    resolved successfully, False on any error.
    """
    for file_path in conflict_files:
        full_path = root / file_path
        try:
            content = full_path.read_text()
        except OSError:
            return False

        lines = content.splitlines(keepends=True)
        resolved_lines: list[str] = []
        in_ours = False
        in_theirs = False

        for line in lines:
            stripped = line.rstrip("\r\n")
            if stripped.startswith("<<<<<<<"):
                in_ours = True
                in_theirs = False
            elif stripped.startswith("=======") and in_ours:
                in_ours = False
                in_theirs = True
            elif stripped.startswith(">>>>>>>") and in_theirs:
                in_theirs = False
            elif in_ours:
                # Skip our side
                pass
            elif in_theirs:
                resolved_lines.append(line)
            else:
                resolved_lines.append(line)

        # If still inside a conflict block the file was malformed
        if in_ours or in_theirs:
            return False

        try:
            full_path.write_text("".join(resolved_lines))
            _run_git("add", file_path, cwd=root)
        except (OSError, subprocess.CalledProcessError):
            return False

    return True


def _check_disjoint_files(session: WorktreeSession, task_index: int, root: Path) -> bool:
    """Return True if the conflicting branch's files don't overlap with already-merged branches.

    Compares files changed by `task_index`'s branch against files changed
    by all already-merged branches. Disjoint means safe for auto-resolve.
    """
    wt = next(
        (w for w in session.worktrees if w.task_index == task_index), None
    )
    if wt is None:
        return False

    try:
        result = _run_git(
            "diff", "--name-only", f"{session.base_commit}..{wt.branch}", cwd=root
        )
        branch_files = set(
            f.strip() for f in result.stdout.strip().split("\n") if f.strip()
        )
    except subprocess.CalledProcessError:
        return False

    merged_files: set[str] = set()
    for merged_index in session.merged_so_far:
        merged_wt = next(
            (w for w in session.worktrees if w.task_index == merged_index), None
        )
        if merged_wt is None:
            continue
        try:
            result = _run_git(
                "diff", "--name-only",
                f"{session.base_commit}..{merged_wt.branch}",
                cwd=root,
            )
            for f in result.stdout.strip().split("\n"):
                f = f.strip()
                if f:
                    merged_files.add(f)
        except subprocess.CalledProcessError:
            continue

    return branch_files.isdisjoint(merged_files)


# ---------------------------------------------------------------------------
# merge_session — Sequential Merge with Conflict Detection
# ---------------------------------------------------------------------------


def merge_session(session: WorktreeSession | None, root: Path) -> MergeResult:
    """Merge agent branches sequentially in task order.

    Skips branches already in merged_so_far. On conflict, returns
    immediately with conflict info (does NOT abort the merge — caller
    decides whether to spawn resolver or abort).
    """
    if session is None:
        raise ValueError(
            "No active worktree session. Create one with create_session() first."
        )

    session.phase = "merging"
    save_session(session, root)

    for task_index in session.merge_order:
        if task_index in session.merged_so_far:
            continue

        # Find worktree info for this task
        wt = next(
            (w for w in session.worktrees if w.task_index == task_index), None
        )
        if wt is None:
            continue

        # Capture agent progress before merge:
        # - completed: branch has commits ahead of base
        # - executing: branch has no commits yet
        ahead = _branch_ahead_count(root, session.base_commit, wt.branch)
        pre_merge_status = "completed" if ahead > 0 else "executing"
        if wt.status != pre_merge_status:
            wt.status = pre_merge_status
            save_session(session, root)

        # Attempt merge
        try:
            _run_git("merge", "--no-ff", wt.branch, cwd=root)
        except subprocess.CalledProcessError as e:
            # Check if this is a merge conflict
            if "CONFLICT" in (e.stdout or "") or "CONFLICT" in (e.stderr or ""):
                # Parse conflicted files
                try:
                    diff_result = _run_git(
                        "diff", "--name-only", "--diff-filter=U", cwd=root
                    )
                    conflict_files = [
                        f.strip()
                        for f in diff_result.stdout.strip().split("\n")
                        if f.strip()
                    ]
                except subprocess.CalledProcessError:
                    conflict_files = []

                # Tier 2: attempt auto-resolve when files are disjoint
                if _check_disjoint_files(session, task_index, root):
                    try:
                        _run_git("merge", "--abort", cwd=root)
                    except subprocess.CalledProcessError:
                        pass
                    # Re-attempt merge to produce conflict markers
                    try:
                        _run_git("merge", "--no-ff", wt.branch, cwd=root)
                    except subprocess.CalledProcessError:
                        pass  # Expected to conflict again
                    if _auto_resolve_keep_incoming(root, conflict_files):
                        try:
                            _run_git("commit", "--no-edit", cwd=root)
                            wt.resolved_tier = "auto-resolve"
                            session.merged_so_far.append(task_index)
                            wt.status = "merged"
                            wt.conflict_files = conflict_files
                            save_session(session, root)
                            continue
                        except subprocess.CalledProcessError:
                            pass
                    # Auto-resolve failed — abort and fall through
                    try:
                        _run_git("merge", "--abort", cwd=root)
                    except subprocess.CalledProcessError:
                        pass

                wt.status = "conflict"
                wt.conflict_files = conflict_files
                save_session(session, root)

                return MergeResult(
                    success=False,
                    merged_indices=list(session.merged_so_far),
                    conflict_index=task_index,
                    conflict_files=conflict_files,
                )
            # Non-conflict git error — re-raise
            raise

        # Clean merge (Tier 1)
        wt.resolved_tier = "clean-merge"
        session.merged_so_far.append(task_index)
        wt.status = "merged"
        save_session(session, root)

    # All merged cleanly
    session.phase = "merged"
    save_session(session, root)

    return MergeResult(
        success=True,
        merged_indices=list(session.merged_so_far),
        conflict_index=None,
        conflict_files=[],
    )


# ---------------------------------------------------------------------------
# get_conflict_context — Prepare Context for Resolver Agent
# ---------------------------------------------------------------------------


def get_conflict_context(
    session: WorktreeSession | None,
    task_index: int,
    plan_json_path: Path,
    root: Path,
) -> dict[str, Any]:
    """Build context dict for the resolver agent.

    Returns conflicted file contents (with markers), the conflicting
    task's action text, and already-merged task descriptions.
    """
    if session is None:
        raise ValueError("No active worktree session.")

    # Find the conflicting worktree
    wt = next(
        (w for w in session.worktrees if w.task_index == task_index), None
    )
    conflict_files = wt.conflict_files if wt else []

    # Read conflicted files (with git markers)
    conflict_content: dict[str, str] = {}
    for file_path in conflict_files:
        full_path = root / file_path
        if full_path.exists():
            conflict_content[file_path] = full_path.read_text()

    # Read plan JSON for task descriptions
    plan_data = json.loads(plan_json_path.read_text())
    tasks = plan_data.get("tasks", [])

    # Get the conflicting task's action
    task_action = ""
    if 0 <= task_index < len(tasks):
        task_action = tasks[task_index].get("action", "")

    # Get already-merged task descriptions
    merged_tasks: list[dict[str, str]] = []
    for idx in session.merged_so_far:
        if 0 <= idx < len(tasks):
            merged_tasks.append(
                {
                    "index": idx,
                    "name": tasks[idx].get("name", ""),
                    "action": tasks[idx].get("action", ""),
                }
            )

    return {
        "conflict_files": conflict_files,
        "conflict_content": conflict_content,
        "task_action": task_action,
        "merged_tasks": merged_tasks,
    }


# ---------------------------------------------------------------------------
# cleanup_session — Remove Worktrees and Branches
# ---------------------------------------------------------------------------


def cleanup_session(session: WorktreeSession | None, root: Path) -> None:
    """Remove all worktrees, delete branches, and remove state file.

    For each worktree not already cleaned:
    1. git worktree remove --force <path>
    2. git branch -D <branch>
    3. Update status to 'cleaned'
    """
    if session is None:
        return

    for wt in session.worktrees:
        if wt.status == "cleaned":
            continue

        # Remove worktree (force in case of uncommitted changes)
        try:
            _run_git("worktree", "remove", "--force", wt.path, cwd=root)
        except subprocess.CalledProcessError:
            # Worktree may already be gone
            pass

        # Delete branch
        try:
            _run_git("branch", "-D", wt.branch, cwd=root)
        except subprocess.CalledProcessError:
            # Branch may already be gone
            pass

        wt.status = "cleaned"
        save_session(session, root)

    # Prune stale worktree references
    try:
        _run_git("worktree", "prune", cwd=root)
    except subprocess.CalledProcessError:
        pass

    # Remove state file
    delete_session_file(root)
