"""Execution flow tracing phase.

BFS from entry points through forward CALLS edges to build process flows.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from scripts.context.model import GraphNode, GraphRelationship, NodeLabel, RelType, generate_id
from scripts.context.phases._utils import is_entry_point
from scripts.context.storage import GraphStorage


@dataclass
class FlowStep:
    node: GraphNode
    depth: int


@dataclass
class FlowResult:
    process_id: str
    entry_point: GraphNode
    steps: list[FlowStep] = field(default_factory=list)


def trace_flows(storage: GraphStorage, max_depth: int = 10) -> list[FlowResult]:
    """BFS from entry points through forward CALLS edges.

    For each entry point:
    1. BFS through outgoing CALLS edges up to max_depth
    2. Create PROCESS node: generate_id(NodeLabel.PROCESS, file_path, entry_name)
    3. Create STEP_IN_PROCESS edges from PROCESS node to each step node
    4. Persist PROCESS nodes and STEP_IN_PROCESS edges to storage

    Returns list of FlowResult.
    """
    all_rels = storage.get_all_relationships_by_types([RelType.CALLS.value])

    # Build adjacency map: source_id -> list[target_id] for CALLS edges
    calls_map: dict[str, list[str]] = {}
    for src, tgt, _ in all_rels:
        calls_map.setdefault(src, []).append(tgt)

    # Gather all nodes to find entry points
    # Use get_all_symbol_nodes to find functions, classes, methods, enums
    symbol_nodes = storage.get_all_symbol_nodes()

    entry_points: list[GraphNode] = [n for n in symbol_nodes if is_entry_point(n)]

    if not entry_points:
        return []

    # Also need to look up nodes by id for BFS
    node_cache: dict[str, GraphNode] = {n.id: n for n in symbol_nodes}

    flow_results: list[FlowResult] = []
    process_nodes: list[GraphNode] = []
    step_edges: list[GraphRelationship] = []

    for entry in entry_points:
        process_id = generate_id(NodeLabel.PROCESS, entry.file_path, entry.name)

        # BFS
        visited: set[str] = {entry.id}
        queue: deque[tuple[str, int]] = deque()
        # enqueue direct callees at depth 1
        for callee_id in calls_map.get(entry.id, []):
            if callee_id not in visited:
                queue.append((callee_id, 1))
                visited.add(callee_id)

        steps: list[FlowStep] = []

        while queue:
            node_id, depth = queue.popleft()
            if depth > max_depth:
                continue

            # Fetch node (may not be a symbol node — try cache first, then storage)
            node = node_cache.get(node_id) or storage.get_node(node_id)
            if node is None:
                continue

            steps.append(FlowStep(node=node, depth=depth))

            if depth < max_depth:
                for callee_id in calls_map.get(node_id, []):
                    if callee_id not in visited:
                        visited.add(callee_id)
                        queue.append((callee_id, depth + 1))

        # Create PROCESS node
        process_node = GraphNode(
            id=process_id,
            label=NodeLabel.PROCESS,
            name=entry.name,
            file_path=entry.file_path,
            is_entry_point=True,
        )
        process_nodes.append(process_node)

        # Create STEP_IN_PROCESS edges
        for step in steps:
            edge_id = f"step_in_process:{process_id}->{step.node.id}"
            step_edges.append(GraphRelationship(
                id=edge_id,
                type=RelType.STEP_IN_PROCESS,
                source=process_id,
                target=step.node.id,
            ))

        flow_results.append(FlowResult(
            process_id=process_id,
            entry_point=entry,
            steps=steps,
        ))

    # Persist process nodes and step edges
    if process_nodes:
        storage.add_nodes(process_nodes)
    if step_edges:
        storage.add_relationships(step_edges)

    return flow_results
