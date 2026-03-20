"""Proximity ranking phase.

BFS from focal nodes (bidirectional) to rank nearby files by graph distance.
"""

from __future__ import annotations

from collections import deque

from scripts.context.model import RelType
from scripts.context.storage import GraphStorage


def rank_by_proximity(
    storage: GraphStorage,
    focal_node_ids: list[str],
    max_depth: int = 5,
) -> list[dict]:
    """Rank files by bidirectional BFS distance from focal nodes.

    Returns a list of dicts sorted by min_distance ascending:
        {"file_path": str, "min_distance": int, "connected_symbols": list[str]}

    Focal nodes' own files are excluded from results.
    """
    if not focal_node_ids:
        return []

    # Pre-fetch all nodes into a cache to avoid N+1 lookups
    node_cache: dict[str, object] = {n.id: n for n in storage.get_all_nodes()}

    # Identify focal files to exclude from results
    focal_files: set[str] = {
        node_cache[nid].file_path
        for nid in focal_node_ids
        if nid in node_cache
    }

    # Build bidirectional adjacency map from CALLS, IMPORTS, EXTENDS, USES_TYPE
    rel_types = [
        RelType.CALLS.value,
        RelType.IMPORTS.value,
        RelType.EXTENDS.value,
        RelType.USES_TYPE.value,
    ]
    all_rels = storage.get_all_relationships_by_types(rel_types)

    adj: dict[str, list[str]] = {}
    for src, tgt, _rel_type in all_rels:
        adj.setdefault(src, []).append(tgt)
        adj.setdefault(tgt, []).append(src)

    # BFS from all focal nodes simultaneously
    visited: set[str] = set(focal_node_ids)
    queue: deque[tuple[str, int]] = deque()
    for focal_id in focal_node_ids:
        queue.append((focal_id, 0))

    node_distances: dict[str, int] = {}

    while queue:
        node_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbor_id in adj.get(node_id, []):
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                node_distances[neighbor_id] = depth + 1
                queue.append((neighbor_id, depth + 1))

    # Group by file_path, skip focal files, track min_distance and symbols
    file_data: dict[str, dict] = {}
    for node_id, distance in node_distances.items():
        node = node_cache.get(node_id)
        if node is None:
            continue
        fp = node.file_path
        if fp in focal_files:
            continue
        if fp not in file_data:
            file_data[fp] = {"min_distance": distance, "connected_symbols": [node.name]}
        else:
            if distance < file_data[fp]["min_distance"]:
                file_data[fp]["min_distance"] = distance
            file_data[fp]["connected_symbols"].append(node.name)

    results = [
        {"file_path": fp, "min_distance": data["min_distance"], "connected_symbols": data["connected_symbols"]}
        for fp, data in file_data.items()
    ]
    results.sort(key=lambda r: r["min_distance"])
    return results
