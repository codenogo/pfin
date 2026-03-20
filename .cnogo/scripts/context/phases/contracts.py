"""Contract detection phase.

Compares stored function/method signatures against current source files
to detect API breaking changes.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from scripts.context.model import GraphNode, NodeLabel


def extract_current_signatures(file_path: str) -> dict[str, str]:
    """Parse a Python file and return {qualified_name: signature_string}.

    Functions are keyed by name, methods by 'ClassName.method_name'.
    Returns empty dict on file not found or syntax error.
    """
    try:
        source = Path(file_path).read_text()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return {}

    lines = source.splitlines()
    sigs: dict[str, str] = {}

    # Build parent map for method detection
    parent_map: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[id(child)] = node

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig_line = lines[node.lineno - 1].strip()
            if sig_line.endswith(":"):
                sig_line = sig_line[:-1].strip()

            parent = parent_map.get(id(node))
            if isinstance(parent, ast.ClassDef):
                key = f"{parent.name}.{node.name}"
            else:
                key = node.name

            sigs[key] = sig_line

    return sigs


def _parse_func_def(sig: str) -> ast.FunctionDef | None:
    """Parse a signature string into an AST FunctionDef node."""
    try:
        source = sig.rstrip(":").strip() + ":\n    pass\n"
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
    except SyntaxError:
        return None
    return None


def _get_param_names(func: ast.FunctionDef) -> list[str]:
    """Extract parameter names from a function def."""
    return [arg.arg for arg in func.args.args]


def _get_defaults_map(func: ast.FunctionDef) -> dict[str, str]:
    """Map parameter names to their default value AST dumps."""
    args = func.args.args
    defaults = func.args.defaults
    result: dict[str, str] = {}
    offset = len(args) - len(defaults)
    for i, d in enumerate(defaults):
        arg_name = args[offset + i].arg
        result[arg_name] = ast.dump(d)
    return result


def _get_return_annotation(func: ast.FunctionDef) -> str | None:
    """Get the AST dump of the return annotation, or None."""
    if func.returns is not None:
        return ast.dump(func.returns)
    return None


def _classify_change(
    old_func: ast.FunctionDef, new_func: ast.FunctionDef
) -> str:
    """Classify the type of signature change."""
    old_names = set(_get_param_names(old_func))
    new_names = set(_get_param_names(new_func))

    if new_names - old_names:
        return "param_added"
    if old_names - new_names:
        return "param_removed"

    old_defaults = _get_defaults_map(old_func)
    new_defaults = _get_defaults_map(new_func)
    if old_defaults != new_defaults:
        return "default_changed"

    old_return = _get_return_annotation(old_func)
    new_return = _get_return_annotation(new_func)
    if old_return != new_return:
        return "return_type_changed"

    return "signature_changed"


def compare_signatures(
    stored_nodes: list[GraphNode],
    current_sigs: dict[str, str],
) -> list[dict[str, Any]]:
    """Compare stored node signatures against current file signatures.

    Returns list of change dicts with keys:
        symbol, change_type, old_signature, new_signature

    Symbols not present in current_sigs are not reported (they may be deleted).
    """
    changes: list[dict[str, Any]] = []

    for node in stored_nodes:
        if node.class_name:
            key = f"{node.class_name}.{node.name}"
        else:
            key = node.name

        if key not in current_sigs:
            continue

        old_sig = node.signature
        new_sig = current_sigs[key]

        if old_sig == new_sig:
            continue

        old_func = _parse_func_def(old_sig)
        new_func = _parse_func_def(new_sig)

        if old_func is None or new_func is None:
            change_type = "signature_changed"
        else:
            change_type = _classify_change(old_func, new_func)

        changes.append({
            "symbol": key,
            "change_type": change_type,
            "old_signature": old_sig,
            "new_signature": new_sig,
        })

    return changes
