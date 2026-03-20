#!/usr/bin/env python3
"""CLI wrapper for the cnogo memory engine.

Usage:
    python3 .cnogo/scripts/workflow_memory.py <command> [options]

Commands:
    init                Initialize memory engine in .cnogo/
    create              Create a new issue
    show <id>           Show issue details
    update <id>         Update issue fields
    claim <id>          Claim an issue
    release <id>        Release an in-progress issue
    close <id>          Close an issue
    report-done <id>    Worker reports task done
    takeover <id>       Leader reassigns a stalled task
    stalled             List stale in-progress tasks
    verify-close <id>   Leader verifies and closes a task
    reopen <id>         Reopen a closed issue
    ready               List ready (unblocked) issues
    list                List issues with filters
    stats               Show aggregate statistics
    dep-add             Add a dependency
    dep-remove          Remove a dependency
    blockers <id>       Show what blocks an issue
    blocks <id>         Show what an issue blocks
    export              Export to JSONL
    import              Import from JSONL
    sync                Export + git add
    prime               Generate context summary
    checkpoint          Generate compact objective/progress checkpoint
    history <id>        Show recent event history for an issue
    phase-get <feature> Get current workflow phase for feature
    phase-set <feature> Set workflow phase for feature
    graph <feature>     Show dependency graph
    session-status      Show active worktree session status
    session-merge       Merge active worktree session branches
    session-cleanup     Cleanup active worktree session
    session-reconcile   Fix orphaned issues after compaction
    graph-index         Index codebase into context graph
    graph-query <name>  Search for symbols by name
    graph-impact <file> Analyze change impact (BFS blast radius)
    graph-context <id>  Show node neighborhood (callers, callees, etc.)
    graph-blast-radius  Compute blast-radius impact for changed files
    graph-search <q>    Full-text search over symbols (BM25 + porter stemming)
    graph-viz           Generate graph visualization (Mermaid or DOT)

No external dependencies. Python 3.9+ required.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure scripts/ is on the path when run directly
_script_dir = Path(__file__).resolve().parent
_repo_root = _script_dir.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _ensure_graph_venv() -> None:
    """Re-exec under .cnogo/.venv/bin/python3 for graph commands."""
    root = _root()
    venv_python = root / ".cnogo" / ".venv" / "bin" / "python3"
    venv_dir = (root / ".cnogo" / ".venv").resolve()
    if Path(sys.prefix).resolve() == venv_dir:
        return  # already in this venv
    if not venv_python.exists():
        req_file = root / ".cnogo" / "requirements-graph.txt"
        print(
            "Graph dependencies not installed.\n"
            "Run:\n"
            f"  python3 -m venv {root / '.cnogo' / '.venv'}\n"
            f"  {venv_python} -m pip install -r {req_file}\n",
            file=sys.stderr,
        )
        raise SystemExit(1)
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)


from scripts.memory import (  # noqa: E402
    blocks,
    blockers,
    checkpoint,
    claim,
    cleanup_session,
    close,
    create,
    dep_add,
    dep_remove,
    export_jsonl,
    get_cost_summary,
    import_jsonl,
    init,
    is_initialized,
    history,
    list_issues,
    load_session,
    get_phase,
    merge_session,
    prime,
    ready,
    reconcile_session,
    record_cost_event,
    release,
    reopen,
    report_done,
    show,
    show_graph,
    stalled_tasks,
    stats,
    set_phase,
    sync,
    takeover_task,
    update,
    verify_and_close,
)


def _root() -> Path:
    """Find repo root by walking up from cwd looking for .git."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".git").exists():
            return p
    return cwd


def _print_issue(issue, *, verbose: bool = False) -> None:
    """Print an issue in human-readable format."""
    status = issue.status
    assignee = f" @{issue.assignee}" if issue.assignee else ""
    prio = f"P{issue.priority}"
    print(f"  [{prio}] {issue.id}  {issue.title}  ({status}{assignee})")
    if verbose:
        if issue.description:
            print(f"        desc: {issue.description[:120]}")
        if issue.feature_slug:
            print(f"        feature: {issue.feature_slug}")
        if getattr(issue, "phase", ""):
            print(f"        phase: {issue.phase}")
        if issue.labels:
            print(f"        labels: {', '.join(issue.labels)}")
        if issue.close_reason:
            print(f"        reason: {issue.close_reason}")


def _print_json(data) -> None:
    """Print as formatted JSON."""
    print(json.dumps(data, indent=2, default=str, sort_keys=True))


def _parse_metadata(raw: str | None) -> dict | None:
    """Parse --metadata JSON and enforce object shape."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid --metadata JSON: {e.msg}") from e
    if not isinstance(parsed, dict):
        raise ValueError("Invalid --metadata JSON: expected an object")
    return parsed


def cmd_init(args: argparse.Namespace) -> int:
    root = _root()
    init(root)
    print(f"Memory engine initialized at {root / '.cnogo'}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    root = _root()
    labels = args.labels.split(",") if args.labels else None
    try:
        metadata = _parse_metadata(args.metadata)
        issue = create(
            args.title,
            issue_type=args.type,
            parent=args.parent,
            feature_slug=args.feature,
            plan_number=args.plan,
            priority=args.priority,
            labels=labels,
            description=args.description,
            metadata=metadata,
            actor=args.actor,
            root=root,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(issue.to_dict())
    else:
        print(f"Created {issue.issue_type}: {issue.id}")
        _print_issue(issue, verbose=True)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    root = _root()
    issue = show(args.id, root=root)
    if not issue:
        print(f"Issue {args.id} not found", file=sys.stderr)
        return 1
    if args.json:
        _print_json(issue.to_dict())
    else:
        _print_issue(issue, verbose=True)
        if issue.deps:
            print("    depends on:")
            for d in issue.deps:
                print(f"      - {d.depends_on_id} ({d.dep_type})")
        if issue.blocks_issues:
            print(f"    blocks: {', '.join(issue.blocks_issues)}")
        if issue.recent_events:
            print("    recent events:")
            for e in issue.recent_events[:5]:
                print(f"      [{e.event_type}] {e.actor} at {e.created_at}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    root = _root()
    try:
        metadata = _parse_metadata(args.metadata)
        issue = update(
            args.id,
            title=args.title,
            description=args.description,
            priority=args.priority,
            metadata=metadata,
            comment=args.comment,
            actor=args.actor,
            root=root,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Updated: {issue.id}")
    _print_issue(issue, verbose=True)
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    root = _root()
    try:
        issue = claim(args.id, actor=args.actor, root=root)
        print(f"Claimed: {issue.id} by {issue.assignee}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_release(args: argparse.Namespace) -> int:
    root = _root()
    try:
        issue = release(args.id, actor=args.actor, actor_role="leader", root=root)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(issue.to_dict())
    else:
        print(f"Released: {issue.id} (status={issue.status})")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    root = _root()
    try:
        issue = close(
            args.id, reason=args.reason, comment=args.comment,
            actor=args.actor, root=root,
        )
        print(f"Closed: {issue.id} ({issue.close_reason})")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_report_done(args: argparse.Namespace) -> int:
    root = _root()
    try:
        outputs = None
        if args.outputs:
            outputs = json.loads(args.outputs)
        issue = report_done(
            args.id, actor=args.actor, outputs=outputs, root=root,
        )
        print(f"Reported done: {issue.id} (state={issue.state})")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_takeover(args: argparse.Namespace) -> int:
    root = _root()
    try:
        payload = takeover_task(
            args.id,
            to_actor=args.to_actor,
            reason=args.reason,
            actor=args.actor,
            root=root,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(payload)
    else:
        print(
            "Takeover:"
            f" {payload['id']} {payload.get('from_actor', '')!r} -> {payload.get('to_actor', '')!r}"
            f" (attempt {payload.get('attempt')}/{payload.get('max_attempts')})"
        )
    return 0


def cmd_stalled(args: argparse.Namespace) -> int:
    root = _root()
    items = stalled_tasks(
        feature_slug=args.feature,
        stale_minutes=args.minutes,
        root=root,
    )
    if args.json:
        _print_json(items)
    elif not items:
        print("No stalled tasks.")
    else:
        print(f"Stalled tasks ({len(items)}):")
        for item in items:
            feature = item.get("feature") or "-"
            print(
                f"  {item['id']}  {item['title']}  "
                f"(stale={item['minutesStale']}m assignee={item.get('assignee') or '-'} feature={feature})"
            )
    return 0


def cmd_verify_close(args: argparse.Namespace) -> int:
    root = _root()
    try:
        issue = verify_and_close(
            args.id, reason=args.reason, actor=args.actor, root=root,
        )
        print(f"Verified and closed: {issue.id} (state={issue.state})")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_reopen(args: argparse.Namespace) -> int:
    root = _root()
    try:
        issue = reopen(args.id, actor=args.actor, root=root)
        print(f"Reopened: {issue.id}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_ready(args: argparse.Namespace) -> int:
    root = _root()
    issues = ready(
        feature_slug=args.feature,
        label=args.label,
        limit=args.limit,
        root=root,
    )
    if args.json:
        _print_json([i.to_dict() for i in issues])
    elif not issues:
        print("No ready issues.")
    else:
        print(f"Ready issues ({len(issues)}):")
        for i in issues:
            _print_issue(i)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = _root()
    issues = list_issues(
        status=args.status,
        issue_type=args.type,
        feature_slug=args.feature,
        parent=args.parent,
        assignee=args.assignee,
        label=args.label,
        limit=args.limit,
        root=root,
    )
    if args.json:
        _print_json([i.to_dict() for i in issues])
    elif not issues:
        print("No issues found.")
    else:
        print(f"Issues ({len(issues)}):")
        for i in issues:
            _print_issue(i)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    root = _root()
    s = stats(root=root)
    if args.json:
        _print_json(s)
    else:
        print(f"Total: {s.get('total', 0)}")
        print(f"  Open: {s.get('open', 0)}")
        print(f"  In Progress: {s.get('in_progress', 0)}")
        print(f"  Closed: {s.get('closed', 0)}")
        print(f"  Ready: {s.get('ready', 0)}")
        print(f"  Blocked: {s.get('blocked', 0)}")
        by_type = s.get("by_type", {})
        if by_type:
            print("  By type:")
            for t, c in sorted(by_type.items()):
                print(f"    {t}: {c}")
        by_feature = s.get("by_feature", {})
        if by_feature:
            print("  By feature:")
            for f, c in sorted(by_feature.items()):
                print(f"    {f}: {c}")
    return 0


def cmd_dep_add(args: argparse.Namespace) -> int:
    root = _root()
    try:
        dep_add(
            args.issue, args.depends_on,
            dep_type=args.type, actor=args.actor, root=root,
        )
        print(f"Dependency added: {args.issue} -> {args.depends_on} ({args.type})")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_dep_remove(args: argparse.Namespace) -> int:
    root = _root()
    dep_remove(args.issue, args.depends_on, actor=args.actor, root=root)
    print(f"Dependency removed: {args.issue} -> {args.depends_on}")
    return 0


def cmd_blockers(args: argparse.Namespace) -> int:
    root = _root()
    issues = blockers(args.id, root=root)
    if not issues:
        print(f"No blockers for {args.id}")
    else:
        print(f"Blockers for {args.id}:")
        for i in issues:
            _print_issue(i)
    return 0


def cmd_blocks(args: argparse.Namespace) -> int:
    root = _root()
    issues = blocks(args.id, root=root)
    if not issues:
        print(f"{args.id} blocks nothing")
    else:
        print(f"{args.id} blocks:")
        for i in issues:
            _print_issue(i)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    root = _root()
    path = export_jsonl(root)
    print(f"Exported to {path}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    root = _root()
    count = import_jsonl(root)
    print(f"Imported {count} issues")
    return 0


def cmd_sync_fn(args: argparse.Namespace) -> int:
    root = _root()
    sync(root)
    print("Synced: exported JSONL and staged for git")
    return 0


def cmd_prime(args: argparse.Namespace) -> int:
    root = _root()
    output = prime(limit=args.limit, verbose=args.verbose, root=root)
    print(output)
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    root = _root()
    output = checkpoint(
        feature_slug=args.feature,
        limit=args.limit,
        root=root,
    )
    print(output)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    root = _root()
    output = history(args.id, limit=args.limit, root=root)
    print(output)
    return 0


def cmd_phase_get(args: argparse.Namespace) -> int:
    root = _root()
    phase = get_phase(args.feature, root=root)
    if args.json:
        _print_json({"feature": args.feature, "phase": phase})
    else:
        print(f"{args.feature}: {phase}")
    return 0


def cmd_phase_set(args: argparse.Namespace) -> int:
    root = _root()
    try:
        count = set_phase(args.feature, args.phase, root=root)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if args.json:
        _print_json({"feature": args.feature, "phase": args.phase, "updated": count})
    else:
        print(f"Set phase for {args.feature}: {args.phase} ({count} issues updated)")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    root = _root()
    output = show_graph(args.feature, root=root)
    print(output)
    return 0


def cmd_session_status(args: argparse.Namespace) -> int:
    root = _root()
    session = load_session(root)
    if args.json:
        _print_json(session.to_dict() if session else {"session": None})
        return 0
    if not session:
        print("No active worktree session")
        return 0
    total = len(session.worktrees)
    done = sum(1 for w in session.worktrees if w.status in {"completed", "merged", "cleaned"})
    print(f"Feature: {session.feature}")
    print(f"Plan: {session.plan_number}")
    print(f"Phase: {session.phase}")
    print(f"Progress: {done}/{total}")
    for wt in session.worktrees:
        print(f"- Task {wt.task_index}: {wt.name} [{wt.status}]")
    return 0


def cmd_session_merge(args: argparse.Namespace) -> int:
    root = _root()
    session = load_session(root)
    if not session:
        payload = {"success": False, "error": "No active worktree session"}
        if args.json:
            _print_json(payload)
        else:
            print(payload["error"])
        return 1
    result = merge_session(session, root)
    tiers = {}
    for wt in session.worktrees:
        if wt.task_index in result.merged_indices:
            tiers[str(wt.task_index)] = wt.resolved_tier or "unknown"
    payload = {
        "success": result.success,
        "merged": result.merged_indices,
        "conflictIndex": result.conflict_index,
        "conflictFiles": result.conflict_files,
        "error": "",
        "tiers": tiers,
    }
    if args.json:
        _print_json(payload)
    else:
        if result.success:
            print(f"Merged tasks: {result.merged_indices}")
        else:
            print(f"Merge stopped at task {result.conflict_index}: {result.conflict_files}")
        tier_counts = {}
        for t in tiers.values():
            tier_counts[t] = tier_counts.get(t, 0) + 1
        if tier_counts:
            print(f"Resolution tiers: {tier_counts}")
    return 0 if result.success else 1


def cmd_session_cleanup(args: argparse.Namespace) -> int:
    root = _root()
    session = load_session(root)
    if not session:
        print("No active worktree session")
        return 0
    cleanup_session(session, root)
    print("Worktrees cleaned")
    return 0


def cmd_session_reconcile(args: argparse.Namespace) -> int:
    from scripts.memory.reconcile import reconcile_session
    root = _root()
    result = reconcile_session(root)
    if getattr(args, 'json', False):
        _print_json(result)
    else:
        for entry in result.get("reconciled", []):
            print(f"Closed: {entry['id']} ({entry.get('status', '')})")
        for entry in result.get("skipped", []):
            print(f"Skipped: {entry['id']} ({entry.get('reason', '')})")
        for entry in result.get("errors", []):
            print(f"Error: {entry['id']}: {entry.get('error', '')}")
        total = len(result.get("reconciled", [])) + len(result.get("skipped", [])) + len(result.get("errors", []))
        if total == 0:
            print("No orphaned issues found")
        else:
            print(f"\nTotal: {len(result.get('reconciled', []))} closed, {len(result.get('skipped', []))} skipped, {len(result.get('errors', []))} errors")
    return 0


def _graph_open(repo: str | None) -> "ContextGraph":
    """Instantiate ContextGraph for the given repo path."""
    from scripts.context import ContextGraph
    return ContextGraph(repo_path=repo or ".")


def _graph_stats(graph: "ContextGraph") -> dict:
    """Get graph stats using available storage methods."""
    node_count = graph._storage.node_count()
    file_count = len(graph._storage.get_indexed_files())
    relationship_count = graph._storage.relationship_count()
    return {"nodes": node_count, "files": file_count, "relationships": relationship_count}


def cmd_graph_index(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    use_json = getattr(args, "json", False)
    use_watch = getattr(args, "watch", False)
    graph = _graph_open(repo)
    try:
        if not use_watch:
            graph.index()
            stats = _graph_stats(graph)
            if use_json:
                print(json.dumps(stats))
            else:
                print(f"Indexed: {stats['nodes']} nodes, {stats['files']} files, {stats['relationships']} relationships")
        else:
            cycle_count = [0]

            def on_cycle(index_stats: dict) -> None:
                cycle_count[0] += 1
                gs = _graph_stats(graph)
                if cycle_count[0] == 1:
                    if use_json:
                        print(json.dumps({"event": "index", **gs}), flush=True)
                        print(json.dumps({"event": "watching"}), flush=True)
                    else:
                        print(f"Indexed: {gs['nodes']} nodes, {gs['files']} files")
                        print("Watching for changes... (Ctrl+C to stop)")
                else:
                    indexed = index_stats.get("files_indexed", 0)
                    removed = index_stats.get("files_removed", 0)
                    changed = indexed + removed
                    if use_json:
                        evt = {"event": "reindex", "files_changed": changed,
                               "files_indexed": indexed, "files_removed": removed,
                               "nodes": gs["nodes"]}
                        print(json.dumps(evt), flush=True)
                    else:
                        print(f"Re-indexed: {changed} files changed, {gs['nodes']} nodes total")

            result = graph.watch(on_cycle=on_cycle)
            if use_json:
                print(json.dumps({"event": "stopped", **result}), flush=True)
            else:
                print("Stopped watching.")
    finally:
        graph.close()
    return 0


def cmd_graph_query(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        results = graph.query(args.name)
        if getattr(args, "json", False):
            print(json.dumps([
                {
                    "id": n.id,
                    "name": n.name,
                    "label": n.label.value,
                    "file_path": n.file_path,
                    "start_line": n.start_line,
                    "end_line": n.end_line,
                }
                for n in results
            ]))
            return 0
        if not results:
            print(f"No nodes matching '{args.name}'")
            return 0
        print(f"{'Name':<30} {'Label':<12} {'File':<40} {'Lines'}")
        print("-" * 90)
        for node in results:
            lines = f"{node.start_line}-{node.end_line}" if node.start_line else "-"
            print(f"{node.name:<30} {node.label.value:<12} {node.file_path:<40} {lines}")
    finally:
        graph.close()
    return 0


def cmd_graph_impact(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        results = graph.impact(args.file_path, max_depth=args.depth)
        if getattr(args, "json", False):
            print(json.dumps([
                {
                    "name": r.node.name,
                    "label": r.node.label.value,
                    "file_path": r.node.file_path,
                    "edge_type": r.edge_type,
                    "depth": r.depth,
                }
                for r in results
            ]))
            return 0
        if not results:
            print(f"No impact found for '{args.file_path}'")
            return 0
        print(f"Impact analysis for {args.file_path} ({len(results)} affected):")
        current_depth = -1
        for r in results:
            if r.depth != current_depth:
                current_depth = r.depth
                print(f"\n  Depth {current_depth}:")
            print(f"    {r.node.name} ({r.node.label.value}) [{r.edge_type}] — {r.node.file_path}")
    finally:
        graph.close()
    return 0


def cmd_graph_dead(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        graph.index()
        results = graph.dead_code()
        if getattr(args, "json", False):
            print(json.dumps([
                {
                    "node_id": r.node_id,
                    "label": r.label.value,
                    "name": r.name,
                    "file_path": r.file_path,
                    "line": r.line,
                }
                for r in results
            ]))
            return 0
        if not results:
            print("0 dead symbols found.")
            return 0
        print(f"{len(results)} dead symbol(s) found:\n")
        for r in results:
            print(f"  DEAD  {r.label.value}:{r.name}  {r.file_path}:{r.line}")
        return 0
    finally:
        graph.close()


def cmd_graph_coupling(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        graph.index()
        threshold = getattr(args, "strength", 0.5)
        results = graph.coupling(threshold=threshold)
        if getattr(args, "json", False):
            print(json.dumps([
                {
                    "source_name": r.source_name,
                    "target_name": r.target_name,
                    "source_id": r.source_id,
                    "target_id": r.target_id,
                    "strength": r.strength,
                    "shared_count": r.shared_count,
                }
                for r in results
            ]))
            return 0
        if not results:
            print("0 coupled symbol pairs found.")
            return 0
        print(f"{len(results)} coupled pair(s) found:\n")
        for r in results:
            print(f"  {r.source_name} <-> {r.target_name}  strength={r.strength} ({r.shared_count} shared)")
        return 0
    finally:
        graph.close()


def cmd_graph_communities(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        min_size = getattr(args, "min_size", 2)
        result = graph.communities(min_size=min_size)
        if getattr(args, "json", False):
            print(json.dumps({
                "communities": [
                    {
                        "community_id": c.community_id,
                        "members": c.members,
                        "member_names": c.member_names,
                        "size": c.size,
                    }
                    for c in result.communities
                ],
                "total_nodes": result.total_nodes,
                "num_communities": result.num_communities,
            }))
            return 0
        if result.num_communities == 0:
            print(f"0 communities found ({result.total_nodes} nodes analyzed).")
            return 0
        print(f"{result.num_communities} community(ies) found ({result.total_nodes} nodes):\n")
        for c in result.communities:
            print(f"  {c.community_id} ({c.size} members):")
            for name in c.member_names:
                print(f"    - {name}")
        return 0
    finally:
        graph.close()


def cmd_graph_flows(args: argparse.Namespace) -> int:
    """Trace execution flows from entry points through forward CALLS edges."""
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        max_depth = getattr(args, "max_depth", 10)
        graph.index()
        flows = graph.flows(max_depth=max_depth)
        if getattr(args, "json", False):
            print(json.dumps([
                {
                    "process_id": f.process_id,
                    "entry_point": {
                        "name": f.entry_point.name,
                        "file_path": f.entry_point.file_path,
                        "label": f.entry_point.label.value,
                    },
                    "steps": [
                        {
                            "name": s.node.name,
                            "file_path": s.node.file_path,
                            "label": s.node.label.value,
                            "depth": s.depth,
                        }
                        for s in f.steps
                    ],
                }
                for f in flows
            ]))
            return 0
        if not flows:
            print("0 execution flows found (no entry points detected).")
            return 0
        print(f"{len(flows)} execution flow(s) found:\n")
        for f in flows:
            print(f"  {f.entry_point.name} ({f.entry_point.file_path}) — {len(f.steps)} step(s)")
            for s in f.steps:
                print(f"    {'  ' * (s.depth - 1)}{s.node.name} (depth {s.depth})")
        return 0
    finally:
        graph.close()


def cmd_graph_status(args: argparse.Namespace) -> int:
    """Report graph existence, counts, and staleness."""
    import hashlib
    repo = getattr(args, "repo", None) or "."
    repo_path = Path(repo).resolve()
    db_path = repo_path / ".cnogo" / "graph.db"

    # Venv health
    venv_python = repo_path / ".cnogo" / ".venv" / "bin" / "python3"
    venv_dir = (repo_path / ".cnogo" / ".venv").resolve()
    venv_ok = venv_python.exists()
    in_venv = Path(sys.prefix).resolve() == venv_dir if venv_ok else False

    if not db_path.exists():
        if getattr(args, "json", False):
            print(json.dumps({"exists": False, "venv": venv_ok, "in_venv": in_venv}))
        else:
            venv_label = "ok" if venv_ok else "missing"
            print(f"Not indexed — no graph.db found. (venv: {venv_label})")
        return 0

    graph = _graph_open(repo)
    try:
        node_count = graph._storage.node_count()
        rel_count = graph._storage.relationship_count()
        file_count = graph._storage.file_count()
        indexed_hashes = graph._storage.get_indexed_files()

        # Check for stale files
        stale_count = 0
        for fpath, old_hash in indexed_hashes.items():
            full = repo_path / fpath
            if not full.exists():
                stale_count += 1
            else:
                try:
                    content = full.read_text(encoding="utf-8")
                    cur_hash = hashlib.sha256(content.encode()).hexdigest()
                    if cur_hash != old_hash:
                        stale_count += 1
                except Exception:
                    stale_count += 1

        if getattr(args, "json", False):
            print(json.dumps({
                "exists": True,
                "nodes": node_count,
                "relationships": rel_count,
                "files": file_count,
                "stale_files": stale_count,
                "venv": venv_ok,
                "in_venv": in_venv,
            }))
        else:
            status = "fresh" if stale_count == 0 else f"{stale_count} stale"
            venv_label = "ok" if venv_ok else "missing"
            print(f"Graph: {node_count} nodes, {rel_count} relationships, {file_count} files ({status}, venv: {venv_label})")
        return 0
    finally:
        graph.close()


def cmd_graph_blast_radius(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        # Determine changed files
        files_arg = getattr(args, "files", None)
        if files_arg:
            changed = [f.strip() for f in files_arg.split(",") if f.strip()]
        else:
            # Auto-detect via git diff
            import subprocess
            try:
                proc = subprocess.run(
                    ["git", "diff", "--name-only"],
                    capture_output=True, text=True, cwd=repo,
                )
                changed = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
            except Exception:
                changed = []

        result = graph.review_impact(changed)

        if getattr(args, "json", False):
            print(json.dumps(result))
            return 0

        total = result["total_affected"]
        if total == 0 and not changed:
            print("No changed files detected. 0 affected symbols.")
            return 0

        print(f"Blast radius for {len(changed)} file(s): {total} affected symbol(s)\n")
        for fpath, entries in result["per_file"].items():
            if entries:
                print(f"  {fpath}:")
                for e in entries:
                    print(f"    {e['name']} ({e['label']}) depth={e['depth']} — {e['file_path']}")
            else:
                print(f"  {fpath}: no impact")
        return 0
    finally:
        graph.close()


def cmd_graph_context(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        ctx = graph.context(args.node_id)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        graph.close()
        return 1
    try:
        node = ctx["node"]
        if getattr(args, "json", False):
            def _nodes_json(nodes):
                return [
                    {"id": n.id, "name": n.name, "label": n.label.value, "file_path": n.file_path}
                    for n in nodes
                ]
            print(json.dumps({
                "node": {"id": node.id, "name": node.name, "label": node.label.value, "file_path": node.file_path},
                "callers": _nodes_json(ctx["callers"]),
                "callees": _nodes_json(ctx["callees"]),
                "importers": _nodes_json(ctx["importers"]),
                "imports": _nodes_json(ctx["imports"]),
                "parent_classes": _nodes_json(ctx["parent_classes"]),
                "child_classes": _nodes_json(ctx["child_classes"]),
            }))
            return 0
        print(f"Node: {node.name} ({node.label.value}) — {node.file_path}")
        for key, label in [
            ("callers", "Callers"),
            ("callees", "Callees"),
            ("importers", "Importers"),
            ("imports", "Imports"),
            ("parent_classes", "Parent classes"),
            ("child_classes", "Child classes"),
        ]:
            items = ctx[key]
            if items:
                print(f"\n  {label} ({len(items)}):")
                for n in items:
                    print(f"    {n.name} ({n.label.value}) — {n.file_path}")
    finally:
        graph.close()
    return 0


def cmd_graph_search(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None) or "."
    graph = _graph_open(repo)
    try:
        limit = getattr(args, "limit", 20)
        results = graph.search(args.query, limit=limit)
        if getattr(args, "json", False):
            print(json.dumps([
                {
                    "name": n.name,
                    "label": n.label.value,
                    "file_path": n.file_path,
                    "start_line": n.start_line,
                    "end_line": n.end_line,
                    "score": score,
                }
                for n, score in results
            ]))
            return 0
        if not results:
            print(f"No results for '{args.query}'")
            return 0
        print(f"{'Name':<30} {'Label':<12} {'File':<40} {'Score'}")
        print("-" * 90)
        for node, score in results:
            print(f"{node.name:<30} {node.label.value:<12} {node.file_path:<40} {score:.4f}")
    finally:
        graph.close()
    return 0


def cmd_graph_contract_check(args: argparse.Namespace) -> int:
    """Detect contract (signature) breaks in changed files and find affected callers."""
    from scripts.context.workflow import contract_warnings

    repo = getattr(args, "repo", None) or "."
    files_arg = getattr(args, "files", None)
    if files_arg:
        changed = [f.strip() for f in files_arg.split(",") if f.strip()]
    else:
        import subprocess
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True, cwd=repo,
            )
            changed = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        except Exception:
            changed = []

    result = contract_warnings(repo, changed_files=changed)

    if getattr(args, "json", False):
        print(json.dumps(result))
        return 0

    if not result.get("enabled"):
        print(f"Graph unavailable: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1

    breaks = result.get("breaks", [])
    summary = result.get("summary", {})

    if not breaks:
        print("No contract breaks detected.")
        return 0

    print(f"Contract breaks: {summary.get('total_breaks', 0)} break(s), "
          f"{summary.get('total_affected_callers', 0)} affected caller(s)\n")
    for brk in breaks:
        print(f"  BREAK  {brk['symbol']}  [{brk['change_type']}]")
        print(f"    old: {brk['old_signature']}")
        print(f"    new: {brk['new_signature']}")
        if brk.get("callers"):
            print(f"    callers ({len(brk['callers'])}):")
            for c in brk["callers"]:
                print(f"      {c['name']} — {c['file']} (confidence={c['confidence']:.2f})")
    return 0


def cmd_graph_suggest_scope(args: argparse.Namespace) -> int:
    from scripts.context.workflow import suggest_scope

    repo = getattr(args, "repo", None) or "."
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else []
    related_files = [f.strip() for f in args.files.split(",")] if getattr(args, "files", None) else []

    result = suggest_scope(repo, keywords=keywords, related_files=related_files)

    if getattr(args, "json", False):
        print(json.dumps(result))
        return 0

    if not result.get("enabled"):
        print(f"Graph unavailable: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1

    suggestions = result.get("suggestions", [])
    if not suggestions:
        print("No scope suggestions found.")
        return 0

    print(f"{'Path':<50} {'Reason':<35} {'Confidence'}")
    print("-" * 95)
    for s in suggestions:
        flag = " (low)" if s.get("low_confidence") else ""
        print(f"{s['path']:<50} {s['reason']:<35} {s['confidence']:.2f}{flag}")
    return 0


def cmd_graph_enrich(args: argparse.Namespace) -> int:
    from scripts.context.workflow import enrich_context

    repo = getattr(args, "repo", None) or "."
    keywords = [k.strip() for k in args.keywords.split(",")]

    result = enrich_context(repo, keywords=keywords)

    if getattr(args, "json", False):
        print(json.dumps(result))
        return 0

    if not result.get("enabled"):
        print(f"Graph unavailable: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1

    related = result.get("related_code", [])
    if not related:
        print("No related code found.")
        return 0

    # Group by relationship type
    by_rel: dict[str, list] = {}
    for r in related:
        by_rel.setdefault(r["relationship"], []).append(r)

    for rel_type, items in sorted(by_rel.items()):
        print(f"\n{rel_type.upper()} ({len(items)}):")
        for item in items:
            print(f"  {item['name']:<30} {item['label']:<12} {item['path']}")

    arch = result.get("architecture", {})
    print(f"\nArchitecture: {arch.get('communities_hint', 0)} files touched")
    return 0


def cmd_graph_validate_scope(args: argparse.Namespace) -> int:
    from scripts.context.workflow import validate_scope

    repo = getattr(args, "repo", None) or "."
    declared = [f.strip() for f in args.declared.split(",")]
    changed = [f.strip() for f in args.changed.split(",")] if getattr(args, "changed", None) else None

    result = validate_scope(repo, declared_files=declared, changed_files=changed)

    if getattr(args, "json", False):
        print(json.dumps(result))
        return 0

    if not result.get("enabled"):
        print(f"Graph unavailable: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1

    status = "WITHIN SCOPE" if result["within_scope"] else "SCOPE VIOLATION"
    print(f"Status: {status}")
    if result["violations"]:
        print(f"\nViolations ({len(result['violations'])}):")
        for v in result["violations"]:
            print(f"  - {v['path']}: {v['reason']}")
    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"  - {w['path']} (confidence: {w['confidence']:.2f}, low)")
    return 0


def cmd_costs(args: argparse.Namespace) -> int:
    if args.project_slug:
        from scripts.memory.costs import summarize_project_costs
        summary = summarize_project_costs(args.project_slug)
        print(f"Project: {summary['project']}")
        print(f"  Input tokens:         {summary['total_input_tokens']:,}")
        print(f"  Output tokens:        {summary['total_output_tokens']:,}")
        print(f"  Cache read tokens:    {summary['total_cache_read_tokens']:,}")
        print(f"  Cache creation tokens:{summary['total_cache_creation_tokens']:,}")
        print(f"  Estimated cost (USD): ${summary['total_estimated_cost_usd']:.4f}")
        if summary["sessions"]:
            print(f"  Sessions ({len(summary['sessions'])}):")
            for s in summary["sessions"]:
                print(f"    {s['path']}  model={s['model']}  tokens={s['tokens']:,}  cost=${s['cost_usd']:.4f}")
    elif args.feature:
        root = _root()
        summary = get_cost_summary(args.feature, root=root)
        print(f"Feature: {summary['feature_slug']}")
        print(f"  Total tokens:     {summary['total_tokens']:,}")
        print(f"  Total cost (USD): ${summary['total_cost_usd']:.4f}")
        print(f"  Events recorded:  {summary['event_count']}")
    else:
        print("Specify --feature or --project-slug")
        return 1
    return 0


def cmd_cost_record(args: argparse.Namespace) -> int:
    from scripts.memory.costs import parse_transcript, estimate_cost
    session_path = Path(args.session_path)
    if not session_path.exists():
        print(f"Error: {session_path} not found", file=sys.stderr)
        return 1
    usage = parse_transcript(session_path)
    cost = estimate_cost(usage)
    record_cost_event(
        args.issue_id,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_tokens=usage.cache_read_tokens + usage.cache_creation_tokens,
        model=usage.model,
        cost_usd=cost,
        root=_root(),
    )
    print(f"Recorded cost event for {args.issue_id}: "
          f"tokens={usage.input_tokens + usage.output_tokens:,}  "
          f"cost=${cost:.4f}  model={usage.model}")
    return 0


def cmd_graph_viz(args: argparse.Namespace) -> int:
    """Generate a graph visualization in Mermaid or DOT format."""
    from scripts.context import ContextGraph

    repo = getattr(args, "repo", None) or "."
    graph = ContextGraph(repo_path=repo)
    try:
        scope = getattr(args, "scope", "full")
        center = getattr(args, "center", None)
        depth = getattr(args, "depth", 3)
        fmt = getattr(args, "format", "mermaid")

        try:
            output = graph.visualize(scope=scope, center=center, depth=depth, format=fmt)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        print(output)
    finally:
        graph.close()
    return 0


def cmd_graph_prioritize(args: argparse.Namespace) -> int:
    """Rank files by graph proximity from focal symbols."""
    from scripts.context.workflow import prioritize_context

    repo = getattr(args, "repo", None) or "."
    symbols_arg = getattr(args, "symbols", None)
    focal_symbols = [s.strip() for s in symbols_arg.split(",")] if symbols_arg else []
    max_files = getattr(args, "max_files", 20)

    result = prioritize_context(repo, focal_symbols=focal_symbols, max_files=max_files)

    if getattr(args, "json", False):
        print(json.dumps(result))
        return 0

    if not result.get("enabled"):
        print(f"Graph unavailable: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1

    ranked = result.get("ranked_files", [])
    if not ranked:
        print("No prioritized files found.")
        return 0

    print(f"{'File':<55} {'Distance':<10} {'Reason'}")
    print("-" * 90)
    for entry in ranked:
        print(f"{entry['path']:<55} {entry['distance']:<10} {entry['reason']}")
    return 0


def cmd_graph_test_coverage(args: argparse.Namespace) -> int:
    """Report test coverage by walking CALLS edges from test file symbols."""
    from scripts.context.workflow import test_coverage_report

    repo = getattr(args, "repo", None) or "."
    result = test_coverage_report(repo)

    if getattr(args, "json", False):
        print(json.dumps(result))
        return 0

    if not result.get("enabled"):
        print(f"Graph unavailable: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1

    summary = result.get("summary", {})
    total = summary.get("total_symbols", 0)
    covered = summary.get("covered", 0)
    uncovered = summary.get("uncovered", 0)
    pct = summary.get("coverage_pct", 0.0)

    print(f"Test coverage: {covered}/{total} symbols ({pct:.1f}%)")
    print(f"  Covered:   {covered}")
    print(f"  Uncovered: {uncovered}")

    by_file = result.get("coverage_by_file", {})
    if by_file:
        print("\nPer file:")
        for fpath, counts in sorted(by_file.items()):
            fc = len(counts.get("covered", []))
            fu = len(counts.get("uncovered", []))
            ftotal = fc + fu
            file_pct = (fc / ftotal * 100.0) if ftotal > 0 else 0.0
            print(f"  {fpath:<50} {fc}/{ftotal} ({file_pct:.0f}%)")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="cnogo Memory Engine CLI",
        prog="workflow_memory",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    sub.add_parser("init", help="Initialize memory engine")

    # create
    p = sub.add_parser("create", help="Create a new issue")
    p.add_argument("title", help="Issue title")
    p.add_argument("--type", default="task",
                   choices=["epic", "task", "subtask", "bug", "quick", "background"])
    p.add_argument("--parent", help="Parent issue ID")
    p.add_argument("--feature", help="Feature slug")
    p.add_argument("--plan", help="Plan number")
    p.add_argument("--priority", type=int, default=2, choices=range(5))
    p.add_argument("--labels", help="Comma-separated labels")
    p.add_argument("--description", help="Description")
    p.add_argument("--metadata", help="JSON metadata")
    p.add_argument("--actor", default="claude")
    p.add_argument("--json", action="store_true")

    # show
    p = sub.add_parser("show", help="Show issue details")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--json", action="store_true")

    # update
    p = sub.add_parser("update", help="Update issue fields")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--title", help="New title")
    p.add_argument("--description", help="New description")
    p.add_argument("--priority", type=int, choices=range(5))
    p.add_argument("--metadata", help="JSON metadata to merge")
    p.add_argument("--comment", help="Add a comment")
    p.add_argument("--actor", default="claude")

    # claim
    p = sub.add_parser("claim", help="Claim an issue")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--actor", default="claude")

    # release
    p = sub.add_parser("release", help="Release an in-progress issue")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--actor", default="leader")
    p.add_argument("--json", action="store_true")

    # close
    p = sub.add_parser("close", help="Close an issue")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--reason", default="completed",
                   choices=["completed", "shipped", "superseded", "wontfix", "cancelled"])
    p.add_argument("--comment", help="Closing comment")
    p.add_argument("--actor", default="claude")

    # report-done
    p = sub.add_parser("report-done", help="Worker reports task done")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--actor", required=True, help="Actor name")
    p.add_argument("--outputs", help="Optional JSON outputs string")

    # takeover
    p = sub.add_parser("takeover", help="Leader takeover/reassignment for a task")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--to", required=True, dest="to_actor", help="Replacement actor")
    p.add_argument("--reason", required=True, help="Why task was taken over")
    p.add_argument("--actor", default="leader")
    p.add_argument("--json", action="store_true")

    # stalled
    p = sub.add_parser("stalled", help="List stale in-progress tasks")
    p.add_argument("--feature", help="Feature slug filter")
    p.add_argument("--minutes", type=int, help="Stale threshold in minutes")
    p.add_argument("--json", action="store_true")

    # verify-close
    p = sub.add_parser("verify-close", help="Leader verifies and closes a task")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--reason", default="completed")
    p.add_argument("--actor", default="claude")

    # reopen
    p = sub.add_parser("reopen", help="Reopen a closed issue")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--actor", default="claude")

    # ready
    p = sub.add_parser("ready", help="List ready issues")
    p.add_argument("--feature", help="Filter by feature slug")
    p.add_argument("--label", help="Filter by label")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")

    # list
    p = sub.add_parser("list", help="List issues")
    p.add_argument("--status", choices=["open", "in_progress", "closed"])
    p.add_argument("--type", choices=["epic", "task", "subtask", "bug", "quick", "background"])
    p.add_argument("--feature", help="Filter by feature slug")
    p.add_argument("--parent", help="Filter by parent issue ID")
    p.add_argument("--assignee", help="Filter by assignee")
    p.add_argument("--label", help="Filter by label")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--json", action="store_true")

    # stats
    p = sub.add_parser("stats", help="Show statistics")
    p.add_argument("--json", action="store_true")

    # dep-add
    p = sub.add_parser("dep-add", help="Add a dependency")
    p.add_argument("issue", help="Blocked issue ID")
    p.add_argument("depends_on", help="Blocker issue ID")
    p.add_argument("--type", default="blocks",
                   choices=["blocks", "parent-child", "related", "discovered-from"])
    p.add_argument("--actor", default="claude")

    # dep-remove
    p = sub.add_parser("dep-remove", help="Remove a dependency")
    p.add_argument("issue", help="Issue ID")
    p.add_argument("depends_on", help="Dependency to remove")
    p.add_argument("--actor", default="claude")

    # blockers
    p = sub.add_parser("blockers", help="Show blockers")
    p.add_argument("id", help="Issue ID")

    # blocks
    p = sub.add_parser("blocks", help="Show what issue blocks")
    p.add_argument("id", help="Issue ID")

    # export
    sub.add_parser("export", help="Export to JSONL")

    # import
    sub.add_parser("import", help="Import from JSONL")

    # sync
    sub.add_parser("sync", help="Export + git add")

    # prime
    p = sub.add_parser("prime", help="Generate context summary")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--verbose", action="store_true", help="Include file hints and restore commands")

    # checkpoint
    p = sub.add_parser("checkpoint", help="Generate compact objective/progress checkpoint")
    p.add_argument("--feature", help="Feature slug (auto-detect if omitted)")
    p.add_argument("--limit", type=int, default=3)

    # history
    p = sub.add_parser("history", help="Show event history for an issue")
    p.add_argument("id", help="Issue ID")
    p.add_argument("--limit", type=int, default=10)

    # phase-get
    p = sub.add_parser("phase-get", help="Get current workflow phase for a feature")
    p.add_argument("feature", help="Feature slug")
    p.add_argument("--json", action="store_true")

    # phase-set
    p = sub.add_parser("phase-set", help="Set workflow phase for a feature")
    p.add_argument("feature", help="Feature slug")
    p.add_argument("phase", choices=["discuss", "plan", "implement", "review", "ship"])
    p.add_argument("--json", action="store_true")

    # graph
    p = sub.add_parser("graph", help="Show dependency graph")
    p.add_argument("feature", help="Feature slug")

    # session-status
    p = sub.add_parser("session-status", help="Show active worktree session")
    p.add_argument("--json", action="store_true")

    # session-merge
    p = sub.add_parser("session-merge", help="Merge active worktree session branches")
    p.add_argument("--json", action="store_true")

    # session-cleanup
    sub.add_parser("session-cleanup", help="Cleanup active worktree session worktrees")

    # session-reconcile
    p = sub.add_parser("session-reconcile", help="Fix orphaned issues after compaction")
    p.add_argument("--json", action="store_true")

    # costs
    p = sub.add_parser("costs", help="Show cost tracking summary")
    p.add_argument("--feature", help="Feature slug to query recorded cost events")
    p.add_argument("--project-slug", help="Claude Code project slug to parse transcripts")

    # cost-record
    p = sub.add_parser("cost-record", help="Parse transcript and record cost event")
    p.add_argument("issue_id", help="Issue ID to attach cost event to")
    p.add_argument("session_path", help="Path to Claude Code session JSONL transcript")

    # graph-index
    p = sub.add_parser("graph-index", help="Index the codebase into the context graph")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--watch", action="store_true", help="Watch for file changes and re-index automatically")

    # graph-query
    p = sub.add_parser("graph-query", help="Search for symbols by name in the context graph")
    p.add_argument("name", help="Symbol name to search for")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-impact
    p = sub.add_parser("graph-impact", help="Analyze change impact for a file")
    p.add_argument("file_path", help="File path to analyze")
    p.add_argument("--depth", type=int, default=3, help="Max BFS depth (default: 3)")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-context
    p = sub.add_parser("graph-context", help="Show context neighborhood for a node")
    p.add_argument("node_id", help="Node ID to inspect")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-dead
    p = sub.add_parser("graph-dead", help="Detect dead (unreferenced) symbols in the context graph")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-coupling
    p = sub.add_parser("graph-coupling", help="Detect structural coupling between symbols (Jaccard similarity)")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--strength", type=float, default=0.5, help="Minimum coupling strength threshold (default: 0.5)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-blast-radius
    p = sub.add_parser("graph-blast-radius", help="Compute blast-radius impact for changed files")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--files", help="Comma-separated file paths (default: auto-detect via git diff)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-communities
    p = sub.add_parser("graph-communities", help="Detect communities of tightly-coupled symbols via label propagation")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--min-size", type=int, default=2, help="Minimum community size (default: 2)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-flows
    p = sub.add_parser("graph-flows", help="Trace execution flows from entry points through CALLS edges")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--max-depth", type=int, default=10, help="Maximum BFS depth (default: 10)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-search
    p = sub.add_parser("graph-search", help="Full-text search over symbol names, signatures, and docstrings")
    p.add_argument("query", help="Search query string")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--limit", type=int, default=20, help="Maximum number of results (default: 20)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-status
    p = sub.add_parser("graph-status", help="Show graph status: existence, counts, and staleness")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-suggest-scope
    p = sub.add_parser("graph-suggest-scope", help="Suggest file scope for a plan based on keyword search and impact analysis")
    p.add_argument("--keywords", help="Comma-separated keywords to search for")
    p.add_argument("--files", help="Comma-separated related file paths for impact analysis")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--limit", type=int, default=20, help="Maximum results per keyword (default: 20)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-validate-scope
    p = sub.add_parser("graph-validate-scope", help="Validate that changes stay within declared file scope via blast-radius analysis")
    p.add_argument("--declared", required=True, help="Comma-separated declared file paths")
    p.add_argument("--changed", help="Comma-separated changed file paths (default: same as declared)")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-enrich
    p = sub.add_parser("graph-enrich", help="Discover related code and architecture for context enrichment")
    p.add_argument("--keywords", required=True, help="Comma-separated keywords to search for")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--limit", type=int, default=20, help="Maximum results per keyword (default: 20)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-contract-check
    p = sub.add_parser("graph-contract-check", help="Detect API contract (signature) breaks in changed files and find affected callers")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--files", help="Comma-separated file paths (default: auto-detect via git diff)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-prioritize
    p = sub.add_parser("graph-prioritize", help="Rank files by graph proximity from focal symbols to prioritize context")
    p.add_argument("--symbols", help="Comma-separated focal symbol names to use as BFS seeds")
    p.add_argument("--max-files", type=int, default=20, dest="max_files",
                   help="Maximum number of files to return (default: 20)")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-test-coverage
    p = sub.add_parser("graph-test-coverage", help="Report test coverage by walking CALLS edges from test file symbols")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # graph-viz
    p = sub.add_parser("graph-viz", help="Generate graph visualization in Mermaid or DOT format")
    p.add_argument("--repo", help="Repository root path (default: cwd)")
    p.add_argument("--format", default="mermaid", choices=["mermaid", "dot"],
                   help="Output format: mermaid or dot (default: mermaid)")
    p.add_argument("--scope", default="full", choices=["file", "module", "full"],
                   help="Subgraph scope: file, module, or full (default: full)")
    p.add_argument("--depth", type=int, default=3,
                   help="Maximum BFS depth from center node (default: 3)")
    p.add_argument("--center", default=None,
                   help="Center node ID for BFS (required for file/module scope)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Check initialization for non-init commands
    # 'costs --project-slug' reads transcripts only, no DB needed
    # 'graph-*' commands use context graph DB, not memory engine DB
    _graph_cmds = {"graph-index", "graph-query", "graph-impact", "graph-context", "graph-dead", "graph-coupling", "graph-blast-radius", "graph-communities", "graph-flows", "graph-search", "graph-status", "graph-suggest-scope", "graph-validate-scope", "graph-enrich", "graph-contract-check", "graph-prioritize", "graph-test-coverage", "graph-viz"}

    if args.command in _graph_cmds:
        _ensure_graph_venv()

    _needs_db = not (args.command == "costs" and getattr(args, "project_slug", None))
    _needs_db = _needs_db and args.command not in _graph_cmds
    if args.command != "init" and _needs_db and not is_initialized(_root()):
        print(
            "Memory engine not initialized. Run: "
            "python3 .cnogo/scripts/workflow_memory.py init",
            file=sys.stderr,
        )
        return 1

    dispatch = {
        "init": cmd_init,
        "create": cmd_create,
        "show": cmd_show,
        "update": cmd_update,
        "claim": cmd_claim,
        "release": cmd_release,
        "close": cmd_close,
        "report-done": cmd_report_done,
        "takeover": cmd_takeover,
        "stalled": cmd_stalled,
        "verify-close": cmd_verify_close,
        "reopen": cmd_reopen,
        "ready": cmd_ready,
        "list": cmd_list,
        "stats": cmd_stats,
        "dep-add": cmd_dep_add,
        "dep-remove": cmd_dep_remove,
        "blockers": cmd_blockers,
        "blocks": cmd_blocks,
        "export": cmd_export,
        "import": cmd_import,
        "sync": cmd_sync_fn,
        "prime": cmd_prime,
        "checkpoint": cmd_checkpoint,
        "history": cmd_history,
        "phase-get": cmd_phase_get,
        "phase-set": cmd_phase_set,
        "graph": cmd_graph,
        "session-status": cmd_session_status,
        "session-merge": cmd_session_merge,
        "session-cleanup": cmd_session_cleanup,
        "session-reconcile": cmd_session_reconcile,
        "costs": cmd_costs,
        "cost-record": cmd_cost_record,
        "graph-index": cmd_graph_index,
        "graph-query": cmd_graph_query,
        "graph-impact": cmd_graph_impact,
        "graph-context": cmd_graph_context,
        "graph-dead": cmd_graph_dead,
        "graph-coupling": cmd_graph_coupling,
        "graph-blast-radius": cmd_graph_blast_radius,
        "graph-communities": cmd_graph_communities,
        "graph-flows": cmd_graph_flows,
        "graph-search": cmd_graph_search,
        "graph-status": cmd_graph_status,
        "graph-suggest-scope": cmd_graph_suggest_scope,
        "graph-validate-scope": cmd_graph_validate_scope,
        "graph-enrich": cmd_graph_enrich,
        "graph-contract-check": cmd_graph_contract_check,
        "graph-prioritize": cmd_graph_prioritize,
        "graph-test-coverage": cmd_graph_test_coverage,
        "graph-viz": cmd_graph_viz,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
