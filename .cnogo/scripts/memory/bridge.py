#!/usr/bin/env python3
"""Bridge between cnogo memory engine and Claude Code Agent Teams.

Translates NN-PLAN.json tasks into structured TaskDesc V2 objects with
memory issue linkage. One-way bridge: memory -> TaskList direction only.

V2 changes from V1:
  - TaskDesc is structured (no baked markdown 'description' field)
  - 'action' is a first-class field
  - 'file_scope' replaces flat 'files' list (adds 'forbidden')
  - 'commands' object groups CLI commands
  - generate_implement_prompt() is a pure renderer (called at spawn-time only)
    with explicit actor_name for strict ownership
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from . import storage as _st
from .identity import generate_child_id as _child_id

_CNOGO_DIR = ".cnogo"
_DB_NAME = "memory.db"

TASK_DESC_SCHEMA_VERSION = 2

# Memory IDs must match: cn-<base36>[.<digits>]*  (e.g., cn-a3f8, cn-a3f8.1.2)
_MEMORY_ID_RE = re.compile(r"^cn-[a-z0-9]+(\.\d+)*$")


def _validate_plan_structure(plan: dict[str, Any]) -> None:
    """Validate plan JSON has required structure. Raises ValueError on violations."""
    feature = plan.get("feature")
    if not isinstance(feature, str) or not feature.strip():
        raise ValueError("Plan missing required non-empty 'feature' string")
    plan_number = plan.get("planNumber")
    if not isinstance(plan_number, str) or not plan_number.strip():
        raise ValueError("Plan missing required non-empty 'planNumber' string")
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Plan 'tasks' must be a non-empty list")
    if len(tasks) > 3:
        raise ValueError(f"Plan has {len(tasks)} tasks; max is 3")
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"Task {i} must be a dict")
        name = task.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Task {i} missing required non-empty 'name' string")
        files = task.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError(f"Task {i} missing required non-empty 'files' list")
        action = task.get("action")
        if not isinstance(action, str) or not action.strip():
            raise ValueError(f"Task {i} missing required non-empty 'action' string")


def plan_to_task_descriptions(
    plan_json_path: Path,
    root: Path,
) -> list[dict[str, Any]]:
    """Read an NN-PLAN.json and generate TaskDesc V2 objects.

    For each task in the plan:
      - If ``memoryId`` is present, use it.
      - If missing, create a memory issue under the plan's ``memoryEpicId``.

    Returns a list of TaskDesc V2 dicts with keys:
      task_id, plan_task_index, title, action, file_scope, commands,
      completion_footer, blockedBy, micro_steps, tdd, skipped
    """
    text = plan_json_path.read_text(encoding="utf-8")
    plan = json.loads(text)
    _validate_plan_structure(plan)

    feature = plan.get("feature", "")
    plan_number = plan.get("planNumber", "")
    epic_id = plan.get("memoryEpicId", "")

    tasks = plan.get("tasks", [])
    task_count = len(tasks)
    results: list[dict[str, Any]] = []

    for i, task in enumerate(tasks):
        memory_id = task.get("memoryId", "")

        # Ensure memory issue exists
        if not memory_id and epic_id:
            memory_id = _ensure_memory_issue(
                root, epic_id, task, feature, plan_number
            )

        title = task.get("name", f"Task {i + 1}")

        # Skip already-completed tasks (duplicate prevention on resume)
        if memory_id and _is_already_closed(root, memory_id):
            results.append(_make_skipped_desc(i, title, memory_id, task))
            continue

        files = task.get("files", [])
        verify = task.get("verify", [])
        blocked_by = task.get("blockedBy", [])
        micro_steps = task.get("microSteps", [])
        tdd = task.get("tdd", {})

        # Validate blockedBy indices are in range and don't self-reference
        for idx in blocked_by:
            if not isinstance(idx, int) or idx < 0 or idx >= task_count:
                raise ValueError(
                    f"Task {i} has invalid blockedBy index {idx} "
                    f"(valid range: 0-{task_count - 1})"
                )
            if idx == i:
                raise ValueError(
                    f"Task {i} has self-referencing blockedBy index {idx}"
                )

        # Build commands object — only non-derivable commands persisted.
        # claim/report_done/context are derived from task_id at render time.
        commands: dict[str, Any] = {"verify": verify}

        # Build completion footer
        completion_footer = f"TASK_DONE: [{memory_id}]" if memory_id else ""

        results.append({
            "task_id": memory_id,
            "plan_task_index": i,
            "title": title,
            "action": task.get("action", ""),
            "file_scope": {
                "paths": files,
                "forbidden": [],
            },
            "commands": commands,
            "completion_footer": completion_footer,
            "blockedBy": blocked_by,
            "micro_steps": micro_steps,
            "tdd": tdd,
            "skipped": False,
        })

    # Post-pass: cascade expansion for tasks with deletions
    cascade_patterns = _load_cascade_patterns(root)
    if cascade_patterns:
        # Collect all file paths already covered by any task
        all_covered: set[str] = set()
        for td in results:
            for p in td.get("file_scope", {}).get("paths", []):
                all_covered.add(p)

        # Build index of non-skipped tasks for next-task lookup
        non_skipped_indices = [
            j for j, td in enumerate(results) if not td.get("skipped", False)
        ]

        for ns_pos, j in enumerate(non_skipped_indices):
            td = results[j]
            plan_task = tasks[td["plan_task_index"]]
            deletions = plan_task.get("deletions", [])
            if not deletions:
                td["auto_expanded_paths"] = []
                continue

            callers = scan_deletion_callers(root, deletions, cascade_patterns)
            uncovered = [c for c in callers if c not in all_covered]
            if not uncovered:
                td["auto_expanded_paths"] = []
                continue

            # Add to the NEXT non-skipped task, or current if no next exists
            if ns_pos + 1 < len(non_skipped_indices):
                target_idx = non_skipped_indices[ns_pos + 1]
            else:
                target_idx = j

            target_td = results[target_idx]
            target_td["file_scope"]["paths"] = list(
                target_td["file_scope"]["paths"]
            ) + uncovered
            target_td.setdefault("auto_expanded_paths", [])
            target_td["auto_expanded_paths"] = (
                target_td["auto_expanded_paths"] + uncovered
            )
            # Mark covered so later iterations don't double-add
            all_covered.update(uncovered)

            # Only clear current task's auto_expanded_paths if it's not
            # the target (avoids overwriting when self-expanding)
            if target_idx != j:
                td["auto_expanded_paths"] = []

    # Ensure all TaskDescV2 dicts have auto_expanded_paths key
    for td in results:
        td.setdefault("auto_expanded_paths", [])

    return results


def generate_implement_prompt(
    taskdesc: dict[str, Any],
    *,
    actor_name: str = "implementer",
) -> str:
    """Render a TaskDesc V2 dict into a markdown agent prompt.

    Pure renderer — called at spawn-time only by team flow.
    Serial flow uses V2 structured fields directly and never calls this.
    """
    title = taskdesc.get("title", "Unknown task")
    action = taskdesc.get("action", "")
    file_scope = taskdesc.get("file_scope", {})
    paths = file_scope.get("paths", [])
    forbidden = file_scope.get("forbidden", [])
    commands = taskdesc.get("commands", {})
    verify = commands.get("verify", [])
    task_id = taskdesc.get("task_id", "")
    completion_footer = taskdesc.get("completion_footer", "")
    micro_steps = taskdesc.get("micro_steps", [])
    tdd = taskdesc.get("tdd", {})
    actor = (actor_name or "implementer").strip() or "implementer"

    lines: list[str] = []

    lines.append(f"# Implement: {title}")
    lines.append("")
    lines.append(action)
    lines.append("")

    if isinstance(micro_steps, list) and micro_steps:
        lines.append("**Micro-steps (execute in order):**")
        for step in micro_steps:
            lines.append(f"- {step}")
        lines.append("")

    if paths:
        lines.append("**Files (ONLY touch these):**")
        lines.append(", ".join(f"`{f}`" for f in paths))
        lines.append("")

    auto_expanded_paths = taskdesc.get("auto_expanded_paths", [])
    if auto_expanded_paths:
        lines.append("**Auto-expanded (callers of deleted files):**")
        for p in auto_expanded_paths:
            lines.append(f"`{p}`")
        lines.append("")

    if forbidden:
        lines.append("**Forbidden (NEVER touch these):**")
        lines.append(", ".join(f"`{f}`" for f in forbidden))
        lines.append("")

    if verify:
        lines.append("**Verify (must ALL pass):**")
        for v in verify:
            lines.append(f"- `{v}`")
        lines.append("")

    if isinstance(tdd, dict) and tdd:
        lines.append("**TDD contract (must provide evidence):**")
        required = tdd.get("required")
        if required is True:
            lines.append("- required: `true`")
            failing = tdd.get("failingVerify", [])
            passing = tdd.get("passingVerify", [])
            lines.append("- failingVerify:")
            if isinstance(failing, list) and failing:
                for cmd in failing:
                    lines.append(f"  - `{cmd}`")
            lines.append("- passingVerify:")
            if isinstance(passing, list) and passing:
                for cmd in passing:
                    lines.append(f"  - `{cmd}`")
        elif required is False:
            lines.append("- required: `false`")
            lines.append(f"- reason: {tdd.get('reason') or '[required in plan contract]'}")
        else:
            lines.append("- required: `[true|false]`")
        lines.append("")

    if task_id:
        if not _MEMORY_ID_RE.match(task_id):
            raise ValueError(
                f"Invalid task_id format: {task_id!r}. "
                "Expected pattern: cn-<base36>[.<digits>]*"
            )
        lines.append(f"**Memory:** `{task_id}`")
        # Derive claim/report_done/context from task_id (not persisted)
        lines.append(
            f"- Claim: `python3 .cnogo/scripts/workflow_memory.py claim {task_id} --actor {actor}`"
        )
        lines.append(
            f"- Report done: `python3 .cnogo/scripts/workflow_memory.py report-done {task_id} --actor {actor}`"
        )
        lines.append(
            f"- Context: `python3 .cnogo/scripts/workflow_memory.py show {task_id}`"
        )
        lines.append(f"- History: `python3 .cnogo/scripts/workflow_memory.py history {task_id}`")
        lines.append("- Checkpoint: `python3 .cnogo/scripts/workflow_memory.py checkpoint`")
        lines.append("")

    lines.append("**On failure:** read history, summarize the last error, fix, and retry.")
    lines.append("**Retry loop:** after each failed verify, run the history command before next attempt.")
    lines.append("After 2 failures, message the team lead.")
    if task_id:
        lines.append("**If blocked:** do NOT report done. Message the team lead.")
        lines.append("**NEVER close issues. Only report done. The leader handles closure.**")
        lines.append("**No rationalization:** never claim done without fresh command evidence.")
        lines.append("")
        lines.append("**On completion:** Add these TWO final lines (in order):")
        lines.append("1) `TASK_EVIDENCE: <single-line JSON>`")
        lines.append(f"2) `{completion_footer}`")
        lines.append("Required TASK_EVIDENCE fields:")
        lines.append("- `verification.commands[]` and `verification.timestamp`")
        lines.append("- `tdd.required` plus failing/passing commands when true, or reason when false")
    lines.append("")

    return "\n".join(lines)


def detect_file_conflicts(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check for file overlaps that may produce merge conflicts (advisory).

    Reads file_scope.paths from TaskDesc V2 dicts. Also warns if any task's
    paths appear in another task's file_scope.forbidden list.

    Returns a list of conflict dicts with keys:
      file, tasks, severity ("advisory" or "forbidden_overlap")

    Empty list = no overlaps detected.
    """
    file_owners: dict[str, list[int]] = {}
    forbidden_map: dict[str, list[int]] = {}

    for i, task in enumerate(tasks):
        if task.get("skipped", False):
            continue
        file_scope = task.get("file_scope", {})
        for f in file_scope.get("paths", []):
            file_owners.setdefault(f, []).append(i)
        for f in file_scope.get("forbidden", []):
            forbidden_map.setdefault(f, []).append(i)

    conflicts = []

    # Path overlaps (same file touched by multiple tasks)
    for file_path, owners in file_owners.items():
        if len(owners) > 1:
            conflicts.append({
                "file": file_path,
                "tasks": owners,
                "severity": "advisory",
            })

    # Forbidden overlaps (a task touches a file another task forbids)
    for file_path, forbidders in forbidden_map.items():
        if file_path in file_owners:
            touchers = file_owners[file_path]
            # Only flag if different tasks are involved
            overlap = [t for t in touchers if t not in forbidders]
            if overlap:
                conflicts.append({
                    "file": file_path,
                    "tasks": overlap,
                    "forbidden_by": forbidders,
                    "severity": "forbidden_overlap",
                })

    return conflicts


def generate_run_id(feature: str) -> str:
    """Generate a unique run ID for a team execution session."""
    return f"{feature}-{int(time.time())}"


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".cnogo"}


def scan_deletion_callers(
    root: Path,
    deletions: list[str],
    cascade_patterns: list[dict],
) -> list[str]:
    """Find files that import/reference modules being deleted.

    For each deletion path, derive the module stem and dotted module path.
    For each cascade pattern, rglob the repo for matching files, read each
    file, and regex-match for the import pattern with {module} substituted.

    Returns a deduplicated list of caller file paths relative to root.
    Skips files inside .git, node_modules, __pycache__, .cnogo.
    """
    callers: list[str] = []
    seen: set[str] = set()

    for deletion in deletions:
        deletion_path = Path(deletion)
        # Derive module stem (e.g., "graphrag" from "src/context/graphrag.py")
        stem = deletion_path.stem
        # Derive dotted module path (e.g., "src.context.graphrag")
        dotted = ".".join(deletion_path.with_suffix("").parts)
        modules = [stem, dotted]

        for pattern in cascade_patterns:
            glob_pattern = pattern.get("glob", "")
            import_pattern_template = pattern.get("importPattern", "")
            if not glob_pattern or not import_pattern_template:
                continue

            # Pre-compile regexes outside the candidate loop
            compiled = []
            for module in modules:
                compiled.append(
                    re.compile(
                        import_pattern_template.replace("{module}", re.escape(module))
                    )
                )

            for candidate in root.rglob(glob_pattern):
                # Skip directories in the skip list
                if any(part in _SKIP_DIRS for part in candidate.parts):
                    continue
                if not candidate.is_file():
                    continue

                try:
                    content = candidate.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                for import_re in compiled:
                    if import_re.search(content):
                        rel = str(candidate.relative_to(root))
                        if rel not in seen:
                            seen.add(rel)
                            callers.append(rel)
                        break  # matched this candidate, no need to try other patterns

    return callers


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_skipped_desc(
    index: int,
    title: str,
    memory_id: str,
    task: dict[str, Any],
) -> dict[str, Any]:
    """Build a skipped TaskDesc V2 dict."""
    return {
        "task_id": memory_id,
        "plan_task_index": index,
        "title": title,
        "action": "",
        "file_scope": {
            "paths": task.get("files", []),
            "forbidden": [],
        },
        "commands": {"verify": task.get("verify", [])},
        "completion_footer": "",
        "blockedBy": task.get("blockedBy", []),
        "micro_steps": task.get("microSteps", []),
        "tdd": task.get("tdd", {}),
        "skipped": True,
    }


def _is_already_closed(root: Path, memory_id: str) -> bool:
    """Check if a memory issue is already completed (for duplicate prevention)."""
    from . import is_initialized, show

    if not is_initialized(root):
        return False
    issue = show(memory_id, root=root)
    if issue is None:
        return False
    return issue.status == "closed" or issue.state in {
        "done_by_worker",
        "verified",
        "closed",
        "ready_to_close",
    }


def _load_cascade_patterns(root: Path) -> list[dict]:
    """Load cascadePatterns from WORKFLOW.json. Returns [] if missing or empty."""
    workflow_path = root / "docs/planning/WORKFLOW.json"
    try:
        text = workflow_path.read_text(encoding="utf-8")
        data = json.loads(text)
        patterns = data.get("cascadePatterns", [])
        return patterns if isinstance(patterns, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _ensure_memory_issue(
    root: Path,
    epic_id: str,
    task: dict[str, Any],
    feature: str,
    plan_number: str,
) -> str:
    """Create a memory issue for a plan task if it doesn't already exist.

    Returns the memory issue ID.
    """
    from . import create, is_initialized

    if not is_initialized(root):
        return ""

    issue = create(
        task.get("name", "Unnamed task"),
        parent=epic_id,
        feature_slug=feature,
        plan_number=plan_number,
        metadata={
            "files": task.get("files", []),
            "verify": task.get("verify", []),
            "microSteps": task.get("microSteps", []),
            "tdd": task.get("tdd", {}),
            "requiresCompletionEvidence": True,
        },
        root=root,
    )
    return issue.id
