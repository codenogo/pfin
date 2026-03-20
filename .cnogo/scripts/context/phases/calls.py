"""Calls phase: creates CALLS relationships with confidence scoring."""
from __future__ import annotations

from scripts.context.model import NodeLabel, RelType, GraphRelationship, generate_id
from scripts.context.storage import GraphStorage
from scripts.context.parser_base import CallInfo, ParseResult


def _build_symbol_index(storage: GraphStorage) -> dict[str, list[str]]:
    """Build a symbol name -> list of node IDs mapping from existing graph nodes.

    Queries storage for all FUNCTION, CLASS, METHOD nodes and indexes them
    by name and by class_name.method_name patterns.

    Returns e.g.:
    {
        "helper": ["function:src/utils.py:helper"],
        "MyClass.do_thing": ["method:src/main.py:MyClass.do_thing"],
        "do_thing": ["method:src/main.py:MyClass.do_thing"],
    }
    """
    rows = storage.get_all_callable_nodes()
    index: dict[str, list[str]] = {}
    for nid, name, class_name, label, file_path in rows:
        index.setdefault(name, []).append(nid)
        if class_name and label == "method":
            qualified = f"{class_name}.{name}"
            index.setdefault(qualified, []).append(nid)
    return index


def _resolve_caller(
    caller_name: str,
    file_path: str,
    symbol_index: dict[str, list[str]],
) -> str | None:
    """Resolve caller name to a node ID.

    caller_name might be:
    - "func_name" -> look up function node
    - "ClassName.method_name" -> look up method node
    - "" -> module-level, use FILE node
    """
    if not caller_name:
        return generate_id(NodeLabel.FILE, file_path, "")

    # Try exact name match in index
    if caller_name in symbol_index:
        # Prefer nodes from the same file
        candidates = symbol_index[caller_name]
        for nid in candidates:
            if file_path in nid:
                return nid
        return candidates[0]

    return None


def _resolve_callee(
    callee_name: str,
    symbol_index: dict[str, list[str]],
) -> tuple[str | None, float]:
    """Resolve callee name to a (node_id, confidence) tuple.

    Resolution strategy:
    1. If callee is "Class.method" -> try qualified match -> confidence 1.0
    2. If callee is simple name -> try function match -> confidence 0.7
    3. If callee contains "." (e.g. "obj.method") -> try method name part -> confidence 0.3

    Returns (node_id, confidence) or (None, 0.0) if unresolvable.
    """
    # Strategy 1: exact qualified match (e.g., "MyClass.do_thing")
    if callee_name in symbol_index:
        return symbol_index[callee_name][0], 1.0

    # Strategy 2: if it contains a dot (e.g., "self.method" or "obj.method")
    if "." in callee_name:
        parts = callee_name.rsplit(".", 1)
        method_name = parts[1]
        # Try to find any method with this name
        if method_name in symbol_index:
            # Found a method — lower confidence since we don't know the type
            return symbol_index[method_name][0], 0.3
        return None, 0.0

    # Strategy 3: simple function name match (not in index at all)
    return None, 0.0


def process_calls(
    parse_results: dict[str, ParseResult],
    storage: GraphStorage,
) -> None:
    """Create CALLS relationships from parse results.

    For each file's calls, resolves caller and callee to graph nodes
    and creates CALLS relationships with confidence scoring.
    Unresolvable calls are silently skipped.
    """
    if not parse_results:
        return

    symbol_index = _build_symbol_index(storage)
    rels: list[GraphRelationship] = []
    seen_rels: set[str] = set()

    for file_path, parse_result in parse_results.items():
        if not parse_result.calls:
            continue

        for call in parse_result.calls:
            caller_id = _resolve_caller(call.caller, file_path, symbol_index)
            if caller_id is None:
                continue

            callee_id, confidence = _resolve_callee(call.callee, symbol_index)
            if callee_id is None:
                continue

            rel_id = f"calls:{caller_id}->{callee_id}"
            if rel_id in seen_rels:
                continue
            seen_rels.add(rel_id)

            rels.append(
                GraphRelationship(
                    id=rel_id,
                    type=RelType.CALLS,
                    source=caller_id,
                    target=callee_id,
                    properties={"confidence": confidence},
                )
            )

    if rels:
        storage.add_relationships(rels)
