"""Shared utilities for context graph phases."""
from __future__ import annotations

from scripts.context.model import GraphNode


def is_entry_point(node: GraphNode) -> bool:
    """Return True if node should be treated as an entry point."""
    if node.is_entry_point:
        return True
    if node.is_exported:
        return True
    if node.name == "main":
        return True
    if node.name.startswith("test_") or node.name.startswith("Test"):
        return True
    if "__init__.py" in node.file_path:
        return True
    return False
