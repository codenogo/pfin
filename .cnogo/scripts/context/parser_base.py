"""Abstract parser base and intermediate representation (IR) dataclasses.

Defines the LanguageParser interface and shared data structures used by
all language-specific parsers. Zero external dependencies — stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SymbolInfo:
    """A symbol (function, class, method, etc.) extracted from source."""

    name: str
    kind: str  # "function", "class", "method", "interface", "type_alias", "enum"
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    class_name: str = ""  # non-empty for methods


@dataclass
class ImportInfo:
    """An import statement extracted from source."""

    module: str
    names: list[str] = field(default_factory=list)
    alias: str = ""
    line: int = 0


@dataclass
class CallInfo:
    """A function/method call extracted from source."""

    caller: str  # enclosing function/method name, "" for module-level
    callee: str
    line: int = 0
    confidence: float = 1.0


@dataclass
class TypeRef:
    """A type reference (annotation, base class, etc.)."""

    name: str
    kind: str  # "annotation", "base_class", "return_type", "generic"
    line: int = 0


@dataclass
class ParseResult:
    """Result of parsing a source file."""

    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    type_refs: list[TypeRef] = field(default_factory=list)
    heritage: list[tuple[str, str, str]] = field(default_factory=list)
    # heritage: (child_class_name, parent_name, "extends"|"implements")
    exports: list[str] = field(default_factory=list)  # exported symbol names


class LanguageParser(ABC):
    """Abstract base for language-specific parsers."""

    @abstractmethod
    def parse(self, content: str, file_path: str = "") -> ParseResult:
        """Parse source content and return extracted IR."""
        ...
