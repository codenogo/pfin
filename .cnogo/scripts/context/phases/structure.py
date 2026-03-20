"""Structure phase: creates FILE and FOLDER nodes with CONTAINS relationships."""
from __future__ import annotations

from pathlib import Path

from scripts.context.model import GraphNode, GraphRelationship, NodeLabel, RelType, generate_id
from scripts.context.storage import GraphStorage
from scripts.context.walker import FileEntry


def process_structure(files: list[FileEntry], storage: GraphStorage) -> None:
    """Create FILE nodes for each file, FOLDER nodes for each directory,
    and CONTAINS relationships (folder->file, parent_folder->child_folder).
    """
    if not files:
        return

    nodes: list[GraphNode] = []
    rels: list[GraphRelationship] = []

    # Collect all unique directory paths from file paths
    seen_folders: set[str] = set()
    folder_pairs: list[tuple[str, str]] = []  # (parent_path_str, child_path_str)

    for entry in files:
        file_path = entry.path  # relative Path

        # Walk up all ancestor directories
        parts = file_path.parts
        for depth in range(len(parts) - 1):
            # Build folder path strings
            child_str = str(Path(*parts[: depth + 1]))
            parent_str = str(Path(*parts[:depth])) if depth > 0 else "."

            if child_str not in seen_folders:
                seen_folders.add(child_str)
                folder_pairs.append((parent_str, child_str))

        # Also ensure root "." exists when any file is at root level
        if len(parts) == 1 and "." not in seen_folders:
            seen_folders.add(".")

    # Create FOLDER nodes
    # Ensure root "." is present whenever there are any folders or root files
    all_root_files = [e for e in files if len(e.path.parts) == 1]
    if seen_folders or (all_root_files and "." not in seen_folders):
        seen_folders.add(".")

    for folder_str in seen_folders:
        folder_id = generate_id(NodeLabel.FOLDER, folder_str, "")
        name = Path(folder_str).name if folder_str != "." else "."
        nodes.append(
            GraphNode(
                id=folder_id,
                label=NodeLabel.FOLDER,
                name=name,
                file_path=folder_str,
            )
        )

    # Create parent->child CONTAINS relationships for nested folders
    for parent_str, child_str in folder_pairs:
        parent_id = generate_id(NodeLabel.FOLDER, parent_str, "")
        child_id = generate_id(NodeLabel.FOLDER, child_str, "")
        rel_id = f"contains:{parent_id}->{child_id}"
        rels.append(
            GraphRelationship(
                id=rel_id,
                type=RelType.CONTAINS,
                source=parent_id,
                target=child_id,
            )
        )

    # Create FILE nodes and folder->file CONTAINS relationships
    for entry in files:
        file_path_str = str(entry.path)
        file_id = generate_id(NodeLabel.FILE, file_path_str, "")
        nodes.append(
            GraphNode(
                id=file_id,
                label=NodeLabel.FILE,
                name=entry.path.name,
                file_path=file_path_str,
                language=entry.language,
                properties={"content_hash": entry.content_hash},
            )
        )

        # Determine parent folder
        parts = entry.path.parts
        if len(parts) == 1:
            parent_folder_str = "."
        else:
            parent_folder_str = str(Path(*parts[:-1]))

        parent_folder_id = generate_id(NodeLabel.FOLDER, parent_folder_str, "")
        rel_id = f"contains:{parent_folder_id}->{file_id}"
        rels.append(
            GraphRelationship(
                id=rel_id,
                type=RelType.CONTAINS,
                source=parent_folder_id,
                target=file_id,
            )
        )

    storage.add_nodes(nodes)
    storage.add_relationships(rels)
