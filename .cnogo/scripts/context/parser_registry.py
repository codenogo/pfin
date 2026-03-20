"""Parser registry for language-specific parsers.

Maps language identifiers to parser instances with lazy initialization
and instance caching.
"""

from __future__ import annotations

from .parser_base import LanguageParser

# Cache for parser instances — reuse across calls.
# None values indicate a language whose parser is unavailable (missing deps).
_PARSER_CACHE: dict[str, LanguageParser | None] = {}


def _create_parser(language: str) -> LanguageParser | None:
    """Create a parser instance for the given language."""
    if language == "python":
        from .parsers.python_parser import PythonParser
        return PythonParser()
    elif language == "typescript":
        from .parsers.typescript_parser import TypeScriptParser
        return TypeScriptParser(tsx=False)
    elif language == "javascript":
        from .parsers.javascript_parser import JavaScriptParser
        return JavaScriptParser()
    elif language == "go":
        from .parsers.go_parser import GoParser
        return GoParser()
    elif language == "rust":
        from .parsers.rust_parser import RustParser
        return RustParser()
    elif language == "java":
        from .parsers.java_parser import JavaParser
        return JavaParser()
    return None


def get_parser(language: str) -> LanguageParser | None:
    """Get a parser for the given language identifier.

    Returns a cached parser instance, or None if the language is not supported
    or its dependencies are unavailable (e.g. tree_sitter not installed).
    """
    if language not in _PARSER_CACHE:
        try:
            parser = _create_parser(language)
        except ImportError:
            parser = None
        _PARSER_CACHE[language] = parser
    return _PARSER_CACHE[language]


def supported_languages() -> list[str]:
    """Return list of languages with parser support."""
    return ["python", "typescript", "javascript", "go", "rust", "java"]


def clear_cache() -> None:
    """Clear the parser cache (useful for testing)."""
    _PARSER_CACHE.clear()
