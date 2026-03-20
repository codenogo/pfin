"""Heritage phase: creates EXTENDS and IMPLEMENTS relationships."""
from __future__ import annotations

from scripts.context.model import RelType, GraphRelationship
from scripts.context.storage import GraphStorage
from scripts.context.parser_base import ParseResult


def _build_class_index(storage: GraphStorage) -> dict[str, str]:
    """Build class/interface/type_alias name -> node ID mapping.

    Query for CLASS, INTERFACE, and TYPE_ALIAS nodes. Return name -> node_id dict.
    """
    rows = storage.get_class_like_nodes()
    index: dict[str, str] = {}
    for nid, name in rows:
        if name not in index:
            index[name] = nid
    return index


def process_heritage(
    parse_results: dict[str, ParseResult],
    storage: GraphStorage,
) -> None:
    """Create EXTENDS/IMPLEMENTS relationships from ParseResult.heritage.

    heritage tuples: (child_name, parent_name, "extends"|"implements")
    """
    if not parse_results:
        return

    class_index = _build_class_index(storage)
    rels: list[GraphRelationship] = []
    seen: set[str] = set()

    for file_path, pr in parse_results.items():
        if not pr.heritage:
            continue

        for child_name, parent_name, kind in pr.heritage:
            child_id = class_index.get(child_name)
            if child_id is None:
                continue

            parent_id = class_index.get(parent_name)
            if parent_id is None:
                continue

            rel_type = RelType.EXTENDS if kind == "extends" else RelType.IMPLEMENTS
            rel_id = f"{rel_type.value}:{child_id}->{parent_id}"
            if rel_id in seen:
                continue
            seen.add(rel_id)

            rels.append(GraphRelationship(
                id=rel_id,
                type=rel_type,
                source=child_id,
                target=parent_id,
            ))

    if rels:
        storage.add_relationships(rels)
