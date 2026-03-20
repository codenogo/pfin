"""Graph visualization module.

Provides Mermaid and DOT/Graphviz renderers for the context graph.
"""

from __future__ import annotations

import re
from collections import deque

from scripts.context.model import GraphNode, RelType
from scripts.context.storage import GraphStorage


def _sanitize_id(node_id: str) -> str:
    """Sanitize a node ID for Mermaid syntax (no colons, slashes, dots)."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", node_id)


def render_mermaid(
    nodes: list[GraphNode],
    edges: list[tuple[str, str, str]],
) -> str:
    """Render a subgraph as Mermaid flowchart syntax."""
    lines = ["flowchart TD"]

    id_map: dict[str, str] = {}
    for node in nodes:
        safe = _sanitize_id(node.id)
        id_map[node.id] = safe
        label_str = node.label.value.upper()
        lines.append(f'    {safe}["{node.name} ({label_str})"]')

    for src, tgt, rel_type in edges:
        safe_src = id_map.get(src, _sanitize_id(src))
        safe_tgt = id_map.get(tgt, _sanitize_id(tgt))
        lines.append(f"    {safe_src} -->|{rel_type}| {safe_tgt}")

    return "\n".join(lines) + "\n"


def render_dot(
    nodes: list[GraphNode],
    edges: list[tuple[str, str, str]],
) -> str:
    """Render a subgraph as DOT/Graphviz digraph syntax."""
    lines = ["digraph G {", "    rankdir=TB;"]

    for node in nodes:
        label_str = node.label.value.upper()
        lines.append(
            f'    "{node.id}" [label="{node.name}\\n{label_str}" shape=box];'
        )

    for src, tgt, rel_type in edges:
        lines.append(f'    "{src}" -> "{tgt}" [label="{rel_type}"];')

    lines.append("}")
    return "\n".join(lines) + "\n"


def _collect_subgraph(
    storage: GraphStorage,
    scope: str,
    center: str | None,
    depth: int,
) -> tuple[list[GraphNode], list[tuple[str, str, str]]]:
    """Collect nodes and edges for visualization based on scope.

    scope="full" or "module": all nodes and edges.
    scope="file": BFS from center node within depth hops.

    Returns (nodes, edges) where edges are (source_id, target_id, rel_type).
    """
    all_rel_types = [rt.value for rt in RelType]
    all_rels = storage.get_all_relationships_by_types(all_rel_types)

    if scope in ("full", "module"):
        all_nodes = storage.get_all_nodes()
        return all_nodes, all_rels

    # scope == "file" — BFS from center
    if center is None:
        all_nodes = storage.get_all_nodes()
        return all_nodes, all_rels

    # Build bidirectional adjacency for BFS
    adj: dict[str, set[str]] = {}
    for src, tgt, _ in all_rels:
        adj.setdefault(src, set()).add(tgt)
        adj.setdefault(tgt, set()).add(src)

    # BFS from center limited by depth
    visited: set[str] = {center}
    queue: deque[tuple[str, int]] = deque([(center, 0)])

    while queue:
        node_id, d = queue.popleft()
        if d >= depth:
            continue
        for neighbor in adj.get(node_id, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, d + 1))

    # Fetch nodes
    nodes: list[GraphNode] = []
    for nid in visited:
        node = storage.get_node(nid)
        if node is not None:
            nodes.append(node)

    # Filter edges to subgraph
    edges = [
        (src, tgt, rt)
        for src, tgt, rt in all_rels
        if src in visited and tgt in visited
    ]

    return nodes, edges
