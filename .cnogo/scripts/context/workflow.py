"""Context graph workflow integration functions.

Each function follows the graceful degradation pattern:
- On success: {enabled: True, ...data...}
- On failure: {enabled: False, error: str}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.context import ContextGraph


def suggest_scope(
    repo_path: str | Path,
    keywords: list[str] | None = None,
    related_files: list[str] | None = None,
) -> dict[str, Any]:
    """Suggest files in scope based on keyword search and impact analysis."""
    try:
        g = ContextGraph(repo_path=repo_path)
    except Exception as e:
        return {"enabled": False, "error": str(e)}

    try:
        suggestions: list[dict] = []
        auto_populate: list[dict] = []
        seen_paths: set[str] = set()

        # Keyword search
        if keywords:
            for kw in keywords:
                results = g.search(kw)
                for node, score in results:
                    if node.file_path and node.file_path not in seen_paths:
                        seen_paths.add(node.file_path)
                        suggestions.append({
                            "path": node.file_path,
                            "reason": f"matches keyword '{kw}'",
                            "confidence": min(score, 1.0),
                        })

        # Impact analysis on related files
        if related_files:
            from scripts.context.phases.impact import impact_analysis

            for fp in related_files:
                # Build edge confidence map: caller_id -> confidence
                # by checking who calls nodes in the changed file
                file_nodes = g._storage.get_nodes_by_file(fp)
                caller_conf_map: dict[str, float] = {}
                for fn in file_nodes:
                    for caller_node, conf in g._storage.get_callers_with_confidence(fn.id):
                        existing = caller_conf_map.get(caller_node.id)
                        if existing is None or conf > existing:
                            caller_conf_map[caller_node.id] = conf

                impacts = impact_analysis(g._storage, fp)
                for ir in impacts:
                    if ir.node.file_path and ir.node.file_path not in seen_paths:
                        seen_paths.add(ir.node.file_path)
                        max_conf = caller_conf_map.get(ir.node.id, 1.0)
                        low_confidence = max_conf <= 0.5
                        entry: dict[str, Any] = {
                            "path": ir.node.file_path,
                            "reason": f"blast radius from {fp}",
                            "confidence": max_conf,
                        }
                        if low_confidence:
                            entry["low_confidence"] = True
                        suggestions.append(entry)

        # Build auto_populate sorted by confidence descending
        auto_populate = sorted(
            [{"path": s["path"], "confidence": s["confidence"]} for s in suggestions],
            key=lambda x: x["confidence"],
            reverse=True,
        )

        return {
            "enabled": True,
            "suggestions": suggestions,
            "auto_populate": auto_populate,
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}
    finally:
        g.close()


def validate_scope(
    repo_path: str | Path,
    declared_files: list[str] | None = None,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Validate that changed files are within declared scope."""
    try:
        g = ContextGraph(repo_path=repo_path)
    except Exception as e:
        return {"enabled": False, "error": str(e)}

    try:
        if declared_files is None:
            declared_files = []
        if changed_files is None:
            changed_files = []

        declared_set = set(declared_files)

        from scripts.context.phases.impact import impact_analysis

        blast_radius: list[dict] = []
        violations: list[dict] = []
        warnings: list[dict] = []

        for fp in changed_files:
            # Build edge confidence map: caller_id -> confidence
            # by checking who calls nodes in the changed file
            file_nodes = g._storage.get_nodes_by_file(fp)
            caller_conf_map: dict[str, float] = {}
            for fn in file_nodes:
                for caller_node, conf in g._storage.get_callers_with_confidence(fn.id):
                    existing = caller_conf_map.get(caller_node.id)
                    if existing is None or conf > existing:
                        caller_conf_map[caller_node.id] = conf

            impacts = impact_analysis(g._storage, fp)
            for ir in impacts:
                if not ir.node.file_path:
                    continue

                max_conf = caller_conf_map.get(ir.node.id, 1.0)
                low_confidence = max_conf <= 0.5

                entry: dict[str, Any] = {
                    "path": ir.node.file_path,
                    "symbol": ir.node.name,
                    "depth": ir.depth,
                    "confidence": max_conf,
                }

                blast_radius.append(entry)

                if ir.node.file_path not in declared_set:
                    if low_confidence:
                        warnings.append({**entry, "low_confidence": True})
                    else:
                        violations.append(entry)

        within_scope = len(violations) == 0

        return {
            "enabled": True,
            "within_scope": within_scope,
            "violations": violations,
            "warnings": warnings,
            "blast_radius": blast_radius,
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}
    finally:
        g.close()


def enrich_context(
    repo_path: str | Path,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Enrich context with related code, callers, callees, and heritage."""
    try:
        g = ContextGraph(repo_path=repo_path)
    except Exception as e:
        return {"enabled": False, "error": str(e)}

    try:
        if keywords is None:
            keywords = []

        from scripts.context.model import RelType

        related_code: list[dict] = []
        seen_node_ids: set[str] = set()

        for kw in keywords:
            results = g.search(kw)
            for node, score in results:
                if node.id in seen_node_ids:
                    continue
                seen_node_ids.add(node.id)

                related_code.append({
                    "path": node.file_path,
                    "name": node.name,
                    "label": node.label.value,
                    "relationship": "self",
                    "confidence": min(score, 1.0),
                    "node_id": node.id,
                })

                # Callers
                callers = g._storage.get_callers_with_confidence(node.id)
                for caller, conf in callers:
                    if caller.id not in seen_node_ids:
                        seen_node_ids.add(caller.id)
                        related_code.append({
                            "path": caller.file_path,
                            "name": caller.name,
                            "label": caller.label.value,
                            "relationship": "caller",
                            "confidence": conf,
                            "node_id": caller.id,
                        })

                # Callees
                callees = g._storage.get_callees(node.id)
                for callee in callees:
                    if callee.id not in seen_node_ids:
                        seen_node_ids.add(callee.id)
                        related_code.append({
                            "path": callee.file_path,
                            "name": callee.name,
                            "label": callee.label.value,
                            "relationship": "callee",
                            "confidence": 1.0,
                            "node_id": callee.id,
                        })

                # Heritage — parents (outgoing EXTENDS)
                parents = g._storage.get_related_nodes(
                    node.id, RelType.EXTENDS, "outgoing"
                )
                for parent in parents:
                    if parent.id not in seen_node_ids:
                        seen_node_ids.add(parent.id)
                        related_code.append({
                            "path": parent.file_path,
                            "name": parent.name,
                            "label": parent.label.value,
                            "relationship": "parent_class",
                            "confidence": 1.0,
                            "node_id": parent.id,
                        })

                # Heritage — children (incoming EXTENDS)
                children = g._storage.get_related_nodes(
                    node.id, RelType.EXTENDS, "incoming"
                )
                for child in children:
                    if child.id not in seen_node_ids:
                        seen_node_ids.add(child.id)
                        related_code.append({
                            "path": child.file_path,
                            "name": child.name,
                            "label": child.label.value,
                            "relationship": "child_class",
                            "confidence": 1.0,
                            "node_id": child.id,
                        })

        return {
            "enabled": True,
            "related_code": related_code,
            "architecture": {},
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}
    finally:
        g.close()


def test_coverage_report(repo_path: str | Path) -> dict[str, Any]:
    """Get test coverage analysis from the context graph."""
    try:
        g = ContextGraph(repo_path=repo_path)
    except Exception as e:
        return {"enabled": False, "error": str(e)}

    try:
        g.index()
        coverage = g.test_coverage()
        return {"enabled": True, **coverage}
    except Exception as e:
        return {"enabled": False, "error": str(e)}
    finally:
        g.close()


def contract_warnings(
    repo_path: str | Path,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Check for contract/signature breaks in changed files."""
    try:
        g = ContextGraph(repo_path=repo_path)
    except Exception as e:
        return {"enabled": False, "error": str(e)}

    try:
        if g._storage.node_count() == 0:
            return {"enabled": False, "error": "graph not indexed"}

        if changed_files is None:
            changed_files = []

        result = g.contract_check(changed_files)
        return {"enabled": True, **result}
    except Exception as e:
        return {"enabled": False, "error": str(e)}
    finally:
        g.close()


def prioritize_context(
    repo_path: str | Path,
    focal_symbols: list[str] | None = None,
    max_files: int = 20,
) -> dict[str, Any]:
    """Rank files by BFS proximity from focal symbols."""
    try:
        g = ContextGraph(repo_path=repo_path)
    except Exception as e:
        return {"enabled": False, "error": str(e)}

    try:
        if not g.is_indexed():
            return {"enabled": False, "error": "Graph not indexed"}

        focal = focal_symbols or []
        results = g.prioritize_files(focal, max_files=max_files)

        ranked_files = [
            {
                "path": r["file_path"],
                "distance": r["min_distance"],
                "reason": f"{len(r['connected_symbols'])} connected symbols",
            }
            for r in results
        ]

        # Track which focal symbols were actually resolved
        resolved: list[str] = []
        if focal:
            for sym_name in focal:
                matches = g._storage.search(sym_name, limit=1)
                for node, _ in matches:
                    if node.name == sym_name:
                        resolved.append(sym_name)
                        break

        return {
            "enabled": True,
            "ranked_files": ranked_files,
            "focal_symbols_resolved": resolved,
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}
    finally:
        g.close()
