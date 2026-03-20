"""Imports phase: creates IMPORTS relationships between files."""
from __future__ import annotations

from pathlib import Path

from scripts.context.model import GraphRelationship, NodeLabel, RelType, generate_id
from scripts.context.storage import GraphStorage
from scripts.context.parser_base import ImportInfo, ParseResult


def build_file_index(storage: GraphStorage) -> dict[str, str]:
    """Build a module-name -> file-path mapping from FILE nodes in storage."""
    file_paths = storage.get_all_file_paths()

    index: dict[str, str] = {}
    for fp in file_paths:
        p = Path(fp)
        stem = str(p.with_suffix(""))

        # Slash-based stem (e.g. "src/utils")
        index[stem] = fp

        # Dot-based stem (e.g. "src.utils")
        dotted = stem.replace("/", ".").replace("\\", ".")
        index[dotted] = fp

        # __init__.py -> package directory
        if p.name == "__init__.py":
            pkg_slash = str(p.parent)
            pkg_dot = pkg_slash.replace("/", ".").replace("\\", ".")
            index[pkg_slash] = fp
            index[pkg_dot] = fp

    return index


def resolve_import(
    imp: ImportInfo,
    source_file: str,
    index: dict[str, str],
) -> str | None:
    """Resolve an ImportInfo to a file path using the file index.

    Returns the resolved file path string, or None if unresolvable.

    Strategy:
    1. Try the module name directly (both dot and slash forms)
    2. For relative imports (module contains a dot-prefixed relative path),
       compute the anchor from source_file's directory
    3. If still unresolved, try stripping the last component (for from-imports
       like "from pkg.mod import name" -> try "pkg/mod")
    """
    module = imp.module
    if not module:
        return None

    # Try direct lookup (dot and slash forms already in index)
    if module in index:
        resolved = index[module]
        if resolved != source_file:
            return resolved

    # Try slash form of a dot-module
    slash_form = module.replace(".", "/")
    if slash_form in index:
        resolved = index[slash_form]
        if resolved != source_file:
            return resolved

    # Try resolving relative to the source file's directory
    source_dir = str(Path(source_file).parent)
    if source_dir != ".":
        # Try "source_dir/module" as both slash and dot
        relative_slash = f"{source_dir}/{slash_form}"
        if relative_slash in index:
            resolved = index[relative_slash]
            if resolved != source_file:
                return resolved

        relative_dot = f"{source_dir.replace('/', '.')}.{module}"
        if relative_dot in index:
            resolved = index[relative_dot]
            if resolved != source_file:
                return resolved

    return None


def process_imports(
    parse_results: dict[str, ParseResult],
    storage: GraphStorage,
) -> None:
    """Create IMPORTS relationships from parse results.

    For each file's imports, resolves the target file and creates an
    IMPORTS relationship from the source FILE node to the target FILE node.
    Unresolvable imports (stdlib, third-party) are silently skipped.
    """
    if not parse_results:
        return

    index = build_file_index(storage)
    rels: list[GraphRelationship] = []
    seen_rels: set[str] = set()

    for file_path, parse_result in parse_results.items():
        if not parse_result.imports:
            continue

        source_id = generate_id(NodeLabel.FILE, file_path, "")

        for imp in parse_result.imports:
            target_path = resolve_import(imp, file_path, index)
            if target_path is None:
                continue

            target_id = generate_id(NodeLabel.FILE, target_path, "")
            rel_id = f"imports:{source_id}->{target_id}"
            if rel_id in seen_rels:
                continue
            seen_rels.add(rel_id)

            rels.append(
                GraphRelationship(
                    id=rel_id,
                    type=RelType.IMPORTS,
                    source=source_id,
                    target=target_id,
                    properties={"symbols": imp.names},
                )
            )

    if rels:
        storage.add_relationships(rels)
