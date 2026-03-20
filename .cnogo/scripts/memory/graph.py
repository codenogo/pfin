#!/usr/bin/env python3
"""Dependency graph operations for the cnogo memory engine.

- Blocked cache materialization (materialized view for O(1) ready checks)
- Cycle detection (DFS before adding edges)
- Topological ordering (Kahn's algorithm)
- Blocker/blocks queries
"""

from __future__ import annotations

import sqlite3


_MAX_ITERATIONS = 10_000


def rebuild_blocked_cache(conn: sqlite3.Connection) -> None:
    """Materialize which issues are blocked by open dependencies.

    Algorithm:
      1. Direct blocking: issues with 'blocks' deps on open issues.
      2. Transitive closure: propagate via both 'blocks' and 'parent-child'
         edges until stable.

    Edge type semantics:
      - 'blocks': direct blocker (B depends on A, A must close first).
      - 'parent-child': transitive only (if parent is blocked, children too).
      An open (non-blocked) parent does NOT directly block its children.

    Uses a temp table to avoid inconsistency during rebuild.
    """
    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _blocked_new"
        " (issue_id TEXT PRIMARY KEY)"
    )
    conn.execute("DELETE FROM _blocked_new")

    # Step 1: Direct blocking — 'blocks' type dependencies on open issues.
    # Only non-closed issues can be blocked (closed issues are done). (W-2)
    conn.execute("""
        INSERT INTO _blocked_new (issue_id)
        SELECT DISTINCT d.issue_id
        FROM dependencies d
        JOIN issues blocker ON d.depends_on_id = blocker.id
        JOIN issues blocked ON d.issue_id = blocked.id
        WHERE d.dep_type = 'blocks'
          AND blocker.status NOT IN ('closed')
          AND blocked.status NOT IN ('closed')
    """)

    # Step 2: Transitive — if a parent/blocker is in _blocked_new,
    # propagate to children and downstream issues.
    # Only propagate to non-closed issues. (W-2)
    for _ in range(_MAX_ITERATIONS):
        cursor = conn.execute("""
            INSERT OR IGNORE INTO _blocked_new (issue_id)
            SELECT DISTINCT d.issue_id
            FROM dependencies d
            JOIN _blocked_new bc ON d.depends_on_id = bc.issue_id
            JOIN issues i ON d.issue_id = i.id
            WHERE d.dep_type IN ('blocks', 'parent-child')
              AND d.issue_id NOT IN (SELECT issue_id FROM _blocked_new)
              AND i.status NOT IN ('closed')
        """)
        if cursor.rowcount == 0:
            break

    # Atomic swap
    conn.execute("DELETE FROM blocked_cache")
    conn.execute("INSERT INTO blocked_cache SELECT * FROM _blocked_new")
    conn.execute("DROP TABLE _blocked_new")


def would_create_cycle(
    conn: sqlite3.Connection,
    issue_id: str,
    depends_on_id: str,
) -> bool:
    """Check if adding issue_id -> depends_on_id creates a cycle.

    Performs DFS from depends_on_id following outgoing edges.
    If we can reach issue_id, a cycle would form.

    Bounded to _MAX_ITERATIONS to prevent DoS on large graphs.
    """
    visited: set[str] = set()
    stack = [depends_on_id]
    iterations = 0
    while stack:
        iterations += 1
        if iterations > _MAX_ITERATIONS:
            raise ValueError(
                f"Cycle detection exceeded {_MAX_ITERATIONS} iterations"
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


def topological_order(conn: sqlite3.Connection) -> list[str]:
    """Return issue IDs in topological order (Kahn's algorithm).

    Only considers open/in_progress issues with 'blocks' or 'parent-child' deps.
    Issues with no dependencies come first.
    """
    # Build in-degree map for non-closed issues
    rows = conn.execute(
        "SELECT id FROM issues WHERE status != 'closed'"
    ).fetchall()
    all_ids = {r["id"] for r in rows}

    in_degree: dict[str, int] = {nid: 0 for nid in all_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in all_ids}

    dep_rows = conn.execute(
        """SELECT d.issue_id, d.depends_on_id
           FROM dependencies d
           WHERE d.dep_type IN ('blocks', 'parent-child')
             AND d.issue_id IN (SELECT id FROM issues WHERE status != 'closed')
             AND d.depends_on_id IN (SELECT id FROM issues WHERE status != 'closed')
        """
    ).fetchall()

    for r in dep_rows:
        blocked = r["issue_id"]
        blocker = r["depends_on_id"]
        if blocked in in_degree and blocker in adj:
            in_degree[blocked] += 1
            adj[blocker].append(blocked)

    # Kahn's: start with zero in-degree nodes
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    queue.sort()  # deterministic ordering
    result: list[str] = []

    while queue:
        current = queue.pop(0)
        result.append(current)
        for neighbor in sorted(adj.get(current, [])):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


def find_cycles(conn: sqlite3.Connection) -> list[list[str]]:
    """Find all cycles in the dependency graph using Tarjan's SCC algorithm.

    Returns list of strongly connected components with size > 1 (cycles).
    """
    rows = conn.execute(
        "SELECT id FROM issues WHERE status != 'closed'"
    ).fetchall()
    all_ids = [r["id"] for r in rows]

    dep_rows = conn.execute(
        """SELECT issue_id, depends_on_id FROM dependencies
           WHERE dep_type IN ('blocks', 'parent-child')"""
    ).fetchall()

    # Build adjacency: issue_id depends on depends_on_id,
    # so edge goes from depends_on_id -> issue_id (blocker -> blocked)
    # For cycle detection, we follow dependency direction: issue -> depends_on
    adj: dict[str, list[str]] = {nid: [] for nid in all_ids}
    for r in dep_rows:
        if r["issue_id"] in adj:
            adj[r["issue_id"]].append(r["depends_on_id"])

    # Tarjan's SCC
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in adj.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            if len(component) > 1:
                sccs.append(component)

    for v in all_ids:
        if v not in index:
            strongconnect(v)

    return sccs
