"""Types phase: creates USES_TYPE relationships."""
from __future__ import annotations

from scripts.context.model import NodeLabel, RelType, GraphRelationship, generate_id
from scripts.context.storage import GraphStorage
from scripts.context.parser_base import ParseResult

PRIMITIVES = {
    "str", "int", "float", "bool", "bytes", "None", "none",
    "string", "number", "boolean", "void", "any", "never",
    "undefined", "null", "object", "unknown",
}


def _build_type_index(storage: GraphStorage) -> dict[str, str]:
    """Build type name -> node ID mapping for CLASS, INTERFACE, TYPE_ALIAS, ENUM."""
    rows = storage.get_type_nodes()
    index: dict[str, str] = {}
    for nid, name in rows:
        if name not in index:
            index[name] = nid
    return index


def process_types(
    parse_results: dict[str, ParseResult],
    storage: GraphStorage,
) -> None:
    """Create USES_TYPE relationships from ParseResult.type_refs.

    Skips: primitives, base_class kind (handled by heritage), unresolvable.
    Source is the FILE node. Target is the resolved type node.
    """
    if not parse_results:
        return

    type_index = _build_type_index(storage)
    rels: list[GraphRelationship] = []
    seen: set[str] = set()

    for file_path, pr in parse_results.items():
        if not pr.type_refs:
            continue

        file_id = generate_id(NodeLabel.FILE, file_path, "")

        for tr in pr.type_refs:
            if tr.kind == "base_class":
                continue
            if tr.name in PRIMITIVES:
                continue

            type_id = type_index.get(tr.name)
            if type_id is None:
                continue

            rel_id = f"uses_type:{file_id}->{type_id}"
            if rel_id in seen:
                continue
            seen.add(rel_id)

            rels.append(GraphRelationship(
                id=rel_id,
                type=RelType.USES_TYPE,
                source=file_id,
                target=type_id,
                properties={"kind": tr.kind},
            ))

    if rels:
        storage.add_relationships(rels)
