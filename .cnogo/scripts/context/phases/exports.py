"""Exports phase: creates EXPORTS relationships."""
from __future__ import annotations

from scripts.context.model import NodeLabel, RelType, GraphRelationship, generate_id
from scripts.context.storage import GraphStorage
from scripts.context.parser_base import ParseResult


def _build_symbol_index_by_file(storage: GraphStorage, file_path: str) -> dict[str, str]:
    """Build symbol name -> node ID mapping for a specific file.

    Returns all FUNCTION, CLASS, METHOD nodes in the given file.
    """
    rows = storage.get_symbol_nodes_by_file(file_path)
    index: dict[str, str] = {}
    for nid, name, class_name in rows:
        if class_name:
            index[f"{class_name}.{name}"] = nid
        index[name] = nid
    return index


def process_exports(
    parse_results: dict[str, ParseResult],
    storage: GraphStorage,
) -> None:
    """Create EXPORTS relationships from ParseResult.exports.

    For each exported symbol name in a file:
    1. Find the symbol node in the graph for that file
    2. Create an EXPORTS relationship from FILE -> symbol

    Unresolvable names are silently skipped.
    """
    if not parse_results:
        return

    rels: list[GraphRelationship] = []
    seen: set[str] = set()

    for file_path, pr in parse_results.items():
        if not pr.exports:
            continue

        file_id = generate_id(NodeLabel.FILE, file_path, "")
        symbol_index = _build_symbol_index_by_file(storage, file_path)

        for name in pr.exports:
            symbol_id = symbol_index.get(name)
            if symbol_id is None:
                continue

            rel_id = f"exports:{file_id}->{symbol_id}"
            if rel_id in seen:
                continue
            seen.add(rel_id)

            rels.append(GraphRelationship(
                id=rel_id,
                type=RelType.EXPORTS,
                source=file_id,
                target=symbol_id,
            ))

    if rels:
        storage.add_relationships(rels)
