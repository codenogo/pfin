"""Symbols phase: creates symbol nodes with DEFINES relationships."""
from __future__ import annotations

from scripts.context.model import GraphNode, GraphRelationship, NodeLabel, RelType, generate_id
from scripts.context.storage import GraphStorage
from scripts.context.parser_base import ParseResult

# Map parser IR kind to NodeLabel
KIND_TO_LABEL: dict[str, NodeLabel] = {
    "function": NodeLabel.FUNCTION,
    "class": NodeLabel.CLASS,
    "method": NodeLabel.METHOD,
    "interface": NodeLabel.INTERFACE,
    "type_alias": NodeLabel.TYPE_ALIAS,
    "enum": NodeLabel.ENUM,
}


def process_symbols(parse_results: dict[str, ParseResult], storage: GraphStorage) -> None:
    """Create symbol nodes from parse results and DEFINES relationships.

    parse_results: mapping of file_path -> ParseResult
    For each symbol in each file's ParseResult.symbols:
    1. Create a GraphNode with appropriate NodeLabel
    2. Create a DEFINES relationship from the FILE node to the symbol node
    """
    nodes: list[GraphNode] = []
    rels: list[GraphRelationship] = []

    for file_path, parse_result in parse_results.items():
        if not parse_result.symbols:
            continue

        file_id = generate_id(NodeLabel.FILE, file_path, "")

        for sym in parse_result.symbols:
            label = KIND_TO_LABEL.get(sym.kind)
            if label is None:
                # Skip unknown symbol kinds
                continue

            # For methods, use "ClassName.method_name" as the symbol name component
            if sym.kind == "method" and sym.class_name:
                symbol_key = f"{sym.class_name}.{sym.name}"
            else:
                symbol_key = sym.name

            symbol_id = generate_id(label, file_path, symbol_key)

            nodes.append(
                GraphNode(
                    id=symbol_id,
                    label=label,
                    name=sym.name,
                    file_path=file_path,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    content=sym.docstring,
                    signature=sym.signature,
                    class_name=sym.class_name,
                )
            )

            rel_id = f"defines:{file_id}->{symbol_id}"
            rels.append(
                GraphRelationship(
                    id=rel_id,
                    type=RelType.DEFINES,
                    source=file_id,
                    target=symbol_id,
                )
            )

    if nodes:
        storage.add_nodes(nodes)
    if rels:
        storage.add_relationships(rels)
