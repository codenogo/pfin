"""Multi-language file walker for the context graph.

Discovers source files across all supported languages, respects .gitignore
patterns and default skip directories. Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Union

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
}

_DEFAULT_SKIP: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".cnogo",
    }
)


@dataclass
class FileEntry:
    """Represents a discovered source file."""

    path: Path
    language: str
    content: str
    content_hash: str


def _load_gitignore(repo_root: Path) -> list[str]:
    """Load .gitignore patterns from repo root, returning a list of patterns."""
    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        return []
    patterns: list[str] = []
    for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_ignored(rel_path: Path, patterns: list[str]) -> bool:
    """Return True if rel_path matches any gitignore pattern."""
    rel_str = str(rel_path).replace(os.sep, "/")
    name = rel_path.name
    for pattern in patterns:
        # Directory patterns like "build/"
        if pattern.endswith("/"):
            dir_pattern = pattern.rstrip("/")
            # Match if any component equals the pattern or the path starts with it
            parts = rel_str.split("/")
            if dir_pattern in parts:
                return True
            if fnmatch.fnmatch(rel_str, dir_pattern + "/*"):
                return True
            if fnmatch.fnmatch(rel_str, dir_pattern):
                return True
        else:
            # Match against filename or full relative path
            if fnmatch.fnmatch(name, pattern):
                return True
            if fnmatch.fnmatch(rel_str, pattern):
                return True
    return False


def walk(repo_path: Union[str, Path]) -> list[FileEntry]:
    """Walk repo_path and return FileEntry objects for all supported source files.

    Skips directories in _DEFAULT_SKIP and files/directories matching .gitignore.
    Returns paths relative to repo_path.
    """
    root = Path(repo_path).resolve()
    gitignore_patterns = _load_gitignore(root)
    entries: list[FileEntry] = []

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root)

        # Prune skipped directories in-place so os.walk won't descend into them
        pruned: list[str] = []
        for d in dirnames:
            if d in _DEFAULT_SKIP:
                continue
            rel_subdir = rel_dir / d if str(rel_dir) != "." else Path(d)
            if _is_ignored(rel_subdir, gitignore_patterns):
                continue
            pruned.append(d)
        dirnames[:] = pruned

        for filename in filenames:
            suffix = Path(filename).suffix
            if suffix not in SUPPORTED_EXTENSIONS:
                continue
            file_path = current / filename
            rel_file = file_path.relative_to(root)
            if _is_ignored(rel_file, gitignore_patterns):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            entries.append(
                FileEntry(
                    path=rel_file,
                    language=SUPPORTED_EXTENSIONS[suffix],
                    content=content,
                    content_hash=content_hash,
                )
            )

    return entries
