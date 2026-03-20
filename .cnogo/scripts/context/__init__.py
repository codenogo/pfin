"""Context graph package — universal multi-language code intelligence engine."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

# Re-export existing symbols (kuzu-free imports only)
from scripts.context.model import NodeLabel, RelType, GraphNode, GraphRelationship, generate_id
from scripts.context.walker import walk, FileEntry
from scripts.context.parser_base import ParseResult
from scripts.context.parser_registry import get_parser

__all__ = ["NodeLabel", "RelType", "GraphNode", "GraphRelationship", "generate_id", "ContextGraph", "FlowResult"]


def __getattr__(name: str):
    if name == "FlowResult":
        from scripts.context.phases.flows import FlowResult
        return FlowResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class ContextGraph:
    """Main API for the universal context graph.

    Usage:
        cg = ContextGraph("/path/to/repo")
        cg.index()         # Build/update the graph
        nodes = cg.query("MyClass")  # Search
        cg.close()
    """

    def __init__(self, repo_path: str | Path, db_path: str | Path | None = None) -> None:
        """Initialize ContextGraph.

        Args:
            repo_path: Root of the repository to index.
            db_path: Path for KuzuDB storage. Defaults to <repo_path>/.cnogo/graph.db/
        """
        self._repo_path = Path(repo_path).resolve()
        if db_path is None:
            db_path = self._repo_path / ".cnogo" / "graph.db"
        self._db_path = Path(db_path)
        from scripts.context.storage import GraphStorage
        self._storage = GraphStorage(self._db_path)
        self._storage.initialize()
        self._hybrid_search = None  # None = not attempted, False = unavailable

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def index(self) -> dict[str, Any]:
        """Run the full indexing pipeline.

        Pipeline: walk → hash check → remove stale → structure → parse → symbols → imports → calls → heritage → types → exports

        Returns dict with stats: {"files_indexed": int, "files_skipped": int, "files_removed": int}
        """
        # 0. Reset HybridSearch so next search() rebuilds against updated storage
        self._hybrid_search = None

        # 1. Walk the repo
        all_files = walk(self._repo_path)

        # 2. Hash check — compare with stored hashes for incremental indexing
        stored_hashes = self._storage.get_indexed_files()

        new_or_changed: list[FileEntry] = []
        unchanged_entries: dict[str, FileEntry] = {}
        current_paths: set[str] = set()
        skipped = 0

        for entry in all_files:
            fp = str(entry.path)
            current_paths.add(fp)
            if stored_hashes.get(fp) == entry.content_hash:
                skipped += 1
                unchanged_entries[fp] = entry
                continue
            new_or_changed.append(entry)

        # 3. Remove stale files (files that were indexed but no longer exist)
        removed = 0
        for old_fp in stored_hashes:
            if old_fp not in current_paths:
                self._storage.remove_nodes_by_file(old_fp)
                self._storage.remove_file_hash(old_fp)
                removed += 1

        # Collect reverse deps BEFORE removing changed-file nodes
        changed_fps = [str(e.path) for e in new_or_changed if str(e.path) in stored_hashes]
        affected_fps = self._storage.get_reverse_dependency_files(changed_fps) if changed_fps else []
        changed_fp_set = {str(e.path) for e in new_or_changed}
        affected_fps = [fp for fp in affected_fps if fp in current_paths and fp not in changed_fp_set]

        # Remove nodes for files that changed (will be re-indexed)
        for entry in new_or_changed:
            fp = str(entry.path)
            if fp in stored_hashes:
                self._storage.remove_nodes_by_file(fp)

        if not new_or_changed:
            return {"files_indexed": 0, "files_skipped": skipped, "files_removed": removed}

        # 4. Structure phase — create FILE and FOLDER nodes
        from scripts.context.phases.structure import process_structure
        process_structure(new_or_changed, self._storage)

        # 5. Parse files concurrently
        parse_results: dict[str, ParseResult] = {}

        def _parse_file(entry: FileEntry) -> tuple[str, ParseResult | None]:
            parser = get_parser(entry.language)
            if parser is None:
                return str(entry.path), None
            return str(entry.path), parser.parse(entry.content, str(entry.path))

        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(_parse_file, e) for e in new_or_changed]
            for future in futures:
                fp, result = future.result()
                if result is not None:
                    parse_results[fp] = result

        # 6. Symbols phase
        from scripts.context.phases.symbols import process_symbols
        process_symbols(parse_results, self._storage)

        # 7. Imports phase
        from scripts.context.phases.imports import process_imports
        process_imports(parse_results, self._storage)

        # 8. Calls phase
        from scripts.context.phases.calls import process_calls
        process_calls(parse_results, self._storage)

        # 9. Heritage phase
        from scripts.context.phases.heritage import process_heritage
        process_heritage(parse_results, self._storage)

        # 10. Types phase
        from scripts.context.phases.types import process_types
        process_types(parse_results, self._storage)

        # 11. Exports phase
        from scripts.context.phases.exports import process_exports
        process_exports(parse_results, self._storage)

        # 12. Rebuild edges for affected unchanged files (reverse deps)
        if affected_fps:
            affected_parse_results: dict[str, ParseResult] = {}
            for fp in affected_fps:
                entry = unchanged_entries.get(fp)
                if entry is None:
                    continue
                parser = get_parser(entry.language)
                if parser is None:
                    continue
                pr = parser.parse(entry.content, fp)
                if pr is not None:
                    affected_parse_results[fp] = pr

            if affected_parse_results:
                # Only remove edge types that will be rebuilt (preserve DEFINES/CONTAINS)
                _rebuild_rel_types = [
                    RelType.IMPORTS.value, RelType.CALLS.value,
                    RelType.EXTENDS.value, RelType.IMPLEMENTS.value,
                    RelType.USES_TYPE.value, RelType.EXPORTS.value,
                ]
                for fp in affected_parse_results:
                    self._storage.remove_edges_from_file_by_types(fp, _rebuild_rel_types)
                # Re-run edge-building phases only (nodes are already correct)
                process_imports(affected_parse_results, self._storage)
                process_calls(affected_parse_results, self._storage)
                process_heritage(affected_parse_results, self._storage)
                process_types(affected_parse_results, self._storage)
                process_exports(affected_parse_results, self._storage)

        # 13. Update file hashes
        for entry in new_or_changed:
            self._storage.update_file_hash(str(entry.path), entry.content_hash)

        return {
            "files_indexed": len(new_or_changed),
            "files_skipped": skipped,
            "files_removed": removed,
        }

    def is_indexed(self) -> bool:
        """Return True if any nodes exist in the graph."""
        return self._storage.node_count() > 0

    def query(self, search_term: str, limit: int = 20) -> list[GraphNode]:
        """Search the graph for nodes matching search_term. Returns nodes only."""
        return [node for node, _score in self._storage.search(search_term, limit=limit)]

    def _get_hybrid_search(self):
        """Lazily initialize HybridSearch. Returns instance or None if unavailable."""
        if self._hybrid_search is False:
            return None
        if self._hybrid_search is not None:
            return self._hybrid_search
        try:
            from scripts.context.search import HybridSearch
            hs = HybridSearch()
            hs.build_index(self._storage)
            self._hybrid_search = hs
            return hs
        except Exception:
            self._hybrid_search = False
            return None

    def search(self, search_term: str, limit: int = 20) -> list[tuple[GraphNode, float]]:
        """Search the graph with relevance scores. Returns (node, score) tuples.

        Tries HybridSearch (BM25+fuzzy+semantic via RRF) first, falls back to
        storage CONTAINS search if HybridSearch is unavailable.
        """
        hs = self._get_hybrid_search()
        if hs is not None:
            results = hs.search(search_term, limit=limit)
            out: list[tuple[GraphNode, float]] = []
            for r in results:
                node = self._storage.get_node(r.node_id)
                if node is not None:
                    out.append((node, r.score))
            return out
        return self._storage.search(search_term, limit=limit)

    def impact(self, file_path: str, max_depth: int = 5) -> list:
        """Return blast-radius impact results for a changed file."""
        from scripts.context.phases.impact import impact_analysis
        return impact_analysis(self._storage, file_path, max_depth)

    def context(self, node_id: str) -> dict[str, Any]:
        """Return full neighborhood for a node.

        Returns dict with keys: node, callers, callees, importers, imports,
        parent_classes, child_classes.  Raises ValueError if not found.
        """
        node = self._storage.get_node(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found")
        # Callers: unwrap (GraphNode, confidence) tuples to plain GraphNode list
        callers = [n for n, _conf in self._storage.get_callers_with_confidence(node_id)]
        callees = self._storage.get_callees(node_id)
        importers = self._storage.get_related_nodes(node_id, RelType.IMPORTS, "incoming")
        imports = self._storage.get_related_nodes(node_id, RelType.IMPORTS, "outgoing")
        parent_classes = (
            self._storage.get_related_nodes(node_id, RelType.EXTENDS, "outgoing")
            + self._storage.get_related_nodes(node_id, RelType.IMPLEMENTS, "outgoing")
        )
        child_classes = (
            self._storage.get_related_nodes(node_id, RelType.EXTENDS, "incoming")
            + self._storage.get_related_nodes(node_id, RelType.IMPLEMENTS, "incoming")
        )
        return {
            "node": node,
            "callers": callers,
            "callees": callees,
            "importers": importers,
            "imports": imports,
            "parent_classes": parent_classes,
            "child_classes": child_classes,
        }

    def callers_with_confidence(self, node_id: str) -> list[tuple[GraphNode, float]]:
        """Return (caller_node, confidence) for all incoming CALLS edges."""
        return self._storage.get_callers_with_confidence(node_id)

    def callees(self, node_id: str) -> list[GraphNode]:
        """Return nodes called by node_id (outgoing CALLS edges)."""
        return self._storage.get_callees(node_id)

    def nodes_in_file(self, file_path: str) -> list[GraphNode]:
        """Return all graph nodes for a given file."""
        return self._storage.get_nodes_by_file(file_path)

    def review_impact(self, changed_files: list[str]) -> dict[str, Any]:
        """Auto-index and return structured impact analysis for changed files."""
        self.index()
        from scripts.context.phases.impact import impact_analysis

        per_file: dict[str, list[dict]] = {}
        all_affected_files: set[str] = set()
        all_affected_symbols: list[str] = []

        for fp in changed_files:
            impacts = impact_analysis(self._storage, fp)
            entries: list[dict] = []
            for ir in impacts:
                entries.append({"name": ir.node.name, "label": ir.node.label.value, "file_path": ir.node.file_path, "depth": ir.depth})
                if ir.node.file_path:
                    all_affected_files.add(ir.node.file_path)
                all_affected_symbols.append(ir.node.name)
            per_file[fp] = entries

        return {
            "graph_status": "indexed",
            "affected_files": sorted(all_affected_files),
            "affected_symbols": all_affected_symbols,
            "per_file": per_file,
            "total_affected": len(all_affected_symbols),
        }

    def test_coverage(self) -> dict[str, Any]:
        """Analyze test coverage based on graph CALLS edges from test files."""
        symbols = self._storage.get_all_symbol_nodes()
        if not symbols:
            return {
                "covered_symbols": [],
                "uncovered_symbols": [],
                "coverage_by_file": {},
                "summary": {"total_symbols": 0, "covered": 0, "uncovered": 0, "coverage_pct": 0.0},
            }

        # Identify test files
        all_nodes = self._storage.get_all_nodes()
        test_node_ids: set[str] = set()
        for n in all_nodes:
            fp = n.file_path or ""
            fname = fp.rsplit("/", 1)[-1] if "/" in fp else fp
            if fname.startswith("test_") or fname.endswith("_test.py") or "/tests/" in fp:
                test_node_ids.add(n.id)

        # Get all CALLS relationships
        calls_rels = self._storage.get_all_relationships_by_types(["calls"])
        # Symbols called from test files are covered
        covered_ids: set[str] = set()
        for src, tgt, _ in calls_rels:
            if src in test_node_ids:
                covered_ids.add(tgt)

        # Also include symbols that are themselves in test files (test functions)
        # but only count non-test, non-file, non-folder symbols for coverage
        non_test_symbols = [
            s for s in symbols
            if s.id not in test_node_ids
            and s.label not in (NodeLabel.FILE, NodeLabel.FOLDER)
        ]

        covered: list[str] = []
        uncovered: list[str] = []
        coverage_by_file: dict[str, dict] = {}

        for sym in non_test_symbols:
            if sym.id in covered_ids:
                covered.append(sym.name)
            else:
                uncovered.append(sym.name)

            fp = sym.file_path or "unknown"
            if fp not in coverage_by_file:
                coverage_by_file[fp] = {"covered": [], "uncovered": []}
            if sym.id in covered_ids:
                coverage_by_file[fp]["covered"].append(sym.name)
            else:
                coverage_by_file[fp]["uncovered"].append(sym.name)

        total = len(non_test_symbols)
        cov_count = len(covered)
        uncov_count = len(uncovered)
        pct = (cov_count / total * 100.0) if total > 0 else 0.0

        return {
            "covered_symbols": covered,
            "uncovered_symbols": uncovered,
            "coverage_by_file": coverage_by_file,
            "summary": {
                "total_symbols": total,
                "covered": cov_count,
                "uncovered": uncov_count,
                "coverage_pct": pct,
            },
        }

    def dead_code(self) -> list:
        """Detect dead (unreferenced) code in the graph."""
        from scripts.context.phases.dead_code import detect_dead_code
        return detect_dead_code(self._storage)

    def coupling(self, threshold: float = 0.1) -> list:
        """Compute Jaccard coupling between symbols."""
        from scripts.context.phases.coupling import compute_coupling
        return compute_coupling(self._storage, threshold)

    def communities(self, min_size: int = 1):
        """Detect communities using Leiden algorithm."""
        from scripts.context.phases.community import detect_communities
        return detect_communities(self._storage, min_size)

    def flows(self, max_depth: int = 10) -> list:
        """Trace execution flows through the call graph."""
        from scripts.context.phases.flows import trace_flows
        return trace_flows(self._storage, max_depth)

    def prioritize_files(self, focal_symbols: list[str], max_files: int = 20) -> list[dict]:
        """Rank files by BFS proximity from focal symbols."""
        from scripts.context.phases.proximity import rank_by_proximity

        if not focal_symbols:
            return []

        # Resolve symbol names to node IDs
        resolved_ids: list[str] = []
        for sym_name in focal_symbols:
            matches = self._storage.search(sym_name, limit=5)
            # Find exact name match
            for node, score in matches:
                if node.name == sym_name:
                    resolved_ids.append(node.id)
                    break

        if not resolved_ids:
            return []

        results = rank_by_proximity(self._storage, resolved_ids, max_depth=3)
        return results[:max_files]

    def contract_check(self, files: list[str]) -> dict[str, Any]:
        """Check for API contract/signature breaks in the given files."""
        from scripts.context.phases.contracts import extract_current_signatures, compare_signatures

        all_breaks: list[dict] = []
        total_affected_callers = 0

        for fp in files:
            stored_nodes = self._storage.get_nodes_by_file(fp)
            # Filter to function/method nodes that have signatures
            sig_nodes = [
                n for n in stored_nodes
                if n.label in (NodeLabel.FUNCTION, NodeLabel.METHOD) and n.signature
            ]
            current_sigs = extract_current_signatures(fp)
            changes = compare_signatures(sig_nodes, current_sigs)

            for change in changes:
                # Enrich with caller information
                # Find the node for this symbol
                matching = [n for n in sig_nodes if n.name == change["symbol"] or
                            (n.class_name and f"{n.class_name}.{n.name}" == change["symbol"])]
                callers_list: list[dict] = []
                if matching:
                    callers = self._storage.get_callers_with_confidence(matching[0].id)
                    for caller_node, conf in callers:
                        callers_list.append({
                            "name": caller_node.name,
                            "file": caller_node.file_path,
                            "confidence": conf,
                        })

                total_affected_callers += len(callers_list)
                all_breaks.append({
                    **change,
                    "callers": callers_list,
                })

        return {
            "breaks": all_breaks,
            "summary": {
                "total_breaks": len(all_breaks),
                "total_affected_callers": total_affected_callers,
            },
        }

    def visualize(self, scope: str, format: str = "mermaid", center: str | None = None, depth: int = 3) -> str:
        """Render the graph as Mermaid or DOT syntax.

        Args:
            scope: "full", "module", or "file"
            format: "mermaid" or "dot"
            center: Node ID for BFS center (used with scope="file")
            depth: BFS depth limit
        """
        valid_scopes = ("full", "module", "file")
        if scope not in valid_scopes:
            raise ValueError(f"Invalid scope '{scope}': must be one of {valid_scopes}")

        valid_formats = ("mermaid", "dot")
        if format not in valid_formats:
            raise ValueError(f"Invalid format '{format}': must be one of {valid_formats}")

        from scripts.context.visualization import render_mermaid, render_dot, _collect_subgraph

        nodes, edges = _collect_subgraph(self._storage, scope, center, depth)

        if format == "dot":
            return render_dot(nodes, edges)
        return render_mermaid(nodes, edges)

    def watch(
        self,
        on_cycle: Callable[[dict[str, Any]], Any] | None = None,
        debounce_ms: int = 1600,
    ) -> dict[str, Any]:
        """Watch for file changes and re-index automatically.

        Runs an initial index(), then watches for source file changes and
        triggers re-indexing on each change batch. Blocks until KeyboardInterrupt.

        Args:
            on_cycle: Optional callback receiving stats dict after each index cycle.
            debounce_ms: Debounce interval in milliseconds for file change batching.

        Returns:
            Cumulative stats: {"total_cycles": int, "total_files_indexed": int, "total_files_removed": int}
        """
        # Lazy import to avoid requiring watchfiles for non-watch usage
        from scripts.context.watcher import FileWatcher

        cumulative = {"total_cycles": 0, "total_files_indexed": 0, "total_files_removed": 0}

        def _run_cycle() -> None:
            stats = self.index()
            cumulative["total_cycles"] += 1
            cumulative["total_files_indexed"] += stats.get("files_indexed", 0)
            cumulative["total_files_removed"] += stats.get("files_removed", 0)
            if on_cycle:
                on_cycle(stats)

        # Initial index
        _run_cycle()

        # Watch for changes
        def _on_change(changes: set) -> None:
            _run_cycle()

        watcher = FileWatcher(self._repo_path, on_change=_on_change, debounce_ms=debounce_ms)
        try:
            watcher.start()
        except KeyboardInterrupt:
            watcher.stop()

        return cumulative

    def close(self) -> None:
        """Close the graph storage."""
        self._storage.close()
