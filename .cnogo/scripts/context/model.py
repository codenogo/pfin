"""Context graph data model.

Defines node types, relationship types, and core dataclasses for the knowledge graph.

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeLabel(Enum):
    """Types of nodes in the context graph."""

    FILE = "file"
    FOLDER = "folder"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"
    COMMUNITY = "community"
    PROCESS = "process"


class RelType(Enum):
    """Types of relationships between nodes."""

    CONTAINS = "contains"
    DEFINES = "defines"
    CALLS = "calls"
    IMPORTS = "imports"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    USES_TYPE = "uses_type"
    EXPORTS = "exports"
    MEMBER_OF = "member_of"
    STEP_IN_PROCESS = "step_in_process"
    COUPLED_WITH = "coupled_with"


def generate_id(label: NodeLabel, file_path: str, symbol_name: str) -> str:
    """Generate a deterministic node ID.

    Format: ``{label.value}:{file_path}:{symbol_name}``
    """
    return f"{label.value}:{file_path}:{symbol_name}"


@dataclass
class GraphNode:
    """A node in the context graph."""

    id: str
    label: NodeLabel
    name: str
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    content: str = ""
    signature: str = ""
    language: str = ""
    class_name: str = ""
    is_dead: bool = False
    is_entry_point: bool = False
    is_exported: bool = False
    properties: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "id": self.id,
            "label": self.label.value,
            "name": self.name,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "signature": self.signature,
            "language": self.language,
            "class_name": self.class_name,
            "is_dead": self.is_dead,
            "is_entry_point": self.is_entry_point,
            "is_exported": self.is_exported,
            "properties": self.properties,
            "embedding": self.embedding,
        }


@dataclass
class GraphRelationship:
    """A directed relationship between two nodes."""

    id: str
    type: RelType
    source: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "target": self.target,
            "properties": self.properties,
        }
