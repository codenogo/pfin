#!/usr/bin/env python3
"""
Shared utilities for workflow scripts.

Consolidates duplicated functions (repo_root, load_json, write_json, load_workflow)
into a single module. All stdlib-only, no external dependencies.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import json
import re
import subprocess
from pathlib import Path
from typing import Any

_repo_root_cache: Path | None = None


def repo_root() -> Path:
    """Return the repository root via git, with cwd fallback."""
    global _repo_root_cache
    if _repo_root_cache is not None:
        return _repo_root_cache
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        _repo_root_cache = Path(out)
    except Exception:
        _repo_root_cache = Path.cwd()
    return _repo_root_cache


def load_json(path: Path) -> Any:
    """Load and parse a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """Write data to a JSON file with 2-space indent and trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n", re.DOTALL)
_LIST_RE = re.compile(r"\[([^\]]*)\]")


def parse_skill_frontmatter(path: Path) -> dict[str, Any]:
    """Parse YAML frontmatter from a skill .md file.

    Returns dict with keys: name (str|None), tags (list[str]),
    appliesTo (list[str]), path (str), raw (str|None).
    Never raises — returns empty defaults for missing/malformed frontmatter.
    """
    result: dict[str, Any] = {
        "name": None,
        "tags": [],
        "appliesTo": [],
        "path": str(path),
        "raw": None,
    }
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return result

    m = _FRONTMATTER_RE.match(text)
    if not m:
        return result

    raw = m.group(1)
    result["raw"] = raw

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if key == "name":
            result["name"] = value if value else None
        elif key in ("tags", "appliesTo"):
            lm = _LIST_RE.search(value)
            if lm:
                items = [s.strip().strip("\"'") for s in lm.group(1).split(",")]
                result[key] = [s for s in items if s]
            elif value:
                result[key] = [value]

    return result


def iter_skill_paths(skills_dir: Path) -> list[Path]:
    """Return flat skill markdown files plus directory-based SKILL.md files."""
    if not skills_dir.is_dir():
        return []

    results: list[Path] = []
    for path in sorted(skills_dir.iterdir()):
        if path.is_file() and path.suffix == ".md":
            results.append(path)
            continue
        if not path.is_dir():
            continue
        skill_md = path / "SKILL.md"
        if skill_md.is_file():
            results.append(skill_md)
    return results


def discover_skills(skills_dir: Path) -> list[dict[str, Any]]:
    """Scan a directory for flat or directory-based skills and parse frontmatter."""
    return [parse_skill_frontmatter(path) for path in iter_skill_paths(skills_dir)]


def load_workflow(root: Path | None = None) -> dict[str, Any]:
    """Load docs/planning/WORKFLOW.json relative to repo root or explicit root."""
    resolved_root = root.resolve() if isinstance(root, Path) else repo_root()
    p = resolved_root / "docs" / "planning" / "WORKFLOW.json"
    if not p.exists():
        return {}
    try:
        cfg = load_json(p)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}
