"""KuzuDB storage backend for the context graph.

Uses a single GraphNode node table (with a ``label`` field) to avoid
the combinatorial explosion of per-label tables.  Relationships are
stored in a CodeRelation rel table.  Properties dicts and embedding
lists are JSON-serialised since KuzuDB does not natively support them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import kuzu

from scripts.context.model import GraphNode, GraphRelationship, NodeLabel, RelType

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_CREATE_NODE_TABLE = """
CREATE NODE TABLE IF NOT EXISTS GraphNode(
    id STRING,
    label STRING,
    name STRING,
    file_path STRING,
    start_line INT64,
    end_line INT64,
    content STRING,
    signature STRING,
    language STRING,
    class_name STRING,
    is_dead BOOLEAN,
    is_entry_point BOOLEAN,
    is_exported BOOLEAN,
    properties STRING,
    embedding STRING,
    PRIMARY KEY(id)
)
"""

_CREATE_REL_TABLE = """
CREATE REL TABLE IF NOT EXISTS CodeRelation(
    FROM GraphNode TO GraphNode,
    rel_id STRING,
    rel_type STRING,
    confidence DOUBLE,
    properties STRING
)
"""

_CREATE_HASH_TABLE = """
CREATE NODE TABLE IF NOT EXISTS FileHash(
    file_path STRING,
    content_hash STRING,
    PRIMARY KEY(file_path)
)
"""

# Column order returned by RETURN n.* on GraphNode (matches CREATE order)
_NODE_COLS = [
    "id", "label", "name", "file_path", "start_line", "end_line",
    "content", "signature", "language", "class_name",
    "is_dead", "is_entry_point", "is_exported", "properties", "embedding",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_node(row: list[Any]) -> GraphNode:
    """Convert a raw KuzuDB row (n.*) into a GraphNode."""
    (
        nid, label, name, file_path, start_line, end_line,
        content, signature, language, class_name,
        is_dead, is_entry_point, is_exported, properties_str, embedding_str,
    ) = row
    return GraphNode(
        id=nid,
        label=NodeLabel(label),
        name=name,
        file_path=file_path or "",
        start_line=start_line or 0,
        end_line=end_line or 0,
        content=content or "",
        signature=signature or "",
        language=language or "",
        class_name=class_name or "",
        is_dead=bool(is_dead),
        is_entry_point=bool(is_entry_point),
        is_exported=bool(is_exported),
        properties=json.loads(properties_str) if properties_str else {},
        embedding=json.loads(embedding_str) if embedding_str else [],
    )


def _node_params(node: GraphNode) -> dict[str, Any]:
    """Build parameter dict for inserting/merging a GraphNode row."""
    return {
        "id": node.id,
        "label": node.label.value,
        "name": node.name,
        "file_path": node.file_path,
        "start_line": node.start_line,
        "end_line": node.end_line,
        "content": node.content,
        "signature": node.signature,
        "language": node.language,
        "class_name": node.class_name,
        "is_dead": node.is_dead,
        "is_entry_point": node.is_entry_point,
        "is_exported": node.is_exported,
        "properties": json.dumps(node.properties),
        "embedding": json.dumps(node.embedding),
    }


# ---------------------------------------------------------------------------
# GraphStorage
# ---------------------------------------------------------------------------


class GraphStorage:
    """KuzuDB-backed graph storage for the context graph."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create database, schema tables, and mark storage ready."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)
        self._conn.execute(_CREATE_NODE_TABLE)
        self._conn.execute(_CREATE_REL_TABLE)
        self._conn.execute(_CREATE_HASH_TABLE)
        self._initialized = True

    def is_initialized(self) -> bool:
        return self._initialized

    def close(self) -> None:
        """Shut down the database connection."""
        if self._conn is not None:
            self._conn = None
        if self._db is not None:
            self._db = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_nodes(self, nodes: list[GraphNode]) -> None:
        """Upsert a list of GraphNode objects."""
        if not nodes:
            return
        conn = self._require_conn()
        for node in nodes:
            p = _node_params(node)
            # MERGE on primary key then SET all fields
            conn.execute(
                """
                MERGE (n:GraphNode {id: $id})
                SET n.label = $label,
                    n.name = $name,
                    n.file_path = $file_path,
                    n.start_line = $start_line,
                    n.end_line = $end_line,
                    n.content = $content,
                    n.signature = $signature,
                    n.language = $language,
                    n.class_name = $class_name,
                    n.is_dead = $is_dead,
                    n.is_entry_point = $is_entry_point,
                    n.is_exported = $is_exported,
                    n.properties = $properties,
                    n.embedding = $embedding
                """,
                p,
            )

    def get_node(self, node_id: str) -> GraphNode | None:
        """Return a single node by ID, or None if not found."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.id = $id RETURN n.*",
            {"id": node_id},
        )
        if result.has_next():
            return _row_to_node(result.get_next())
        return None

    def get_nodes_by_file(self, file_path: str) -> list[GraphNode]:
        """Return all nodes whose file_path matches."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.file_path = $fp RETURN n.*",
            {"fp": file_path},
        )
        nodes: list[GraphNode] = []
        while result.has_next():
            nodes.append(_row_to_node(result.get_next()))
        return nodes

    def node_count(self) -> int:
        """Return total number of nodes in the graph."""
        conn = self._require_conn()
        result = conn.execute("MATCH (n:GraphNode) RETURN count(n)")
        if result.has_next():
            return int(result.get_next()[0])
        return 0

    def relationship_count(self) -> int:
        """Return total number of relationships in the graph."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH ()-[r:CodeRelation]->() RETURN count(r)"
        )
        if result.has_next():
            return int(result.get_next()[0])
        return 0

    def file_count(self) -> int:
        """Return number of FILE-label nodes in the graph."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.label = 'file' RETURN count(n)"
        )
        if result.has_next():
            return int(result.get_next()[0])
        return 0

    def mark_dead_nodes(self, node_ids: list[str]) -> None:
        """Set is_dead=True for the given node IDs."""
        if not node_ids:
            return
        conn = self._require_conn()
        for nid in node_ids:
            conn.execute(
                "MATCH (n:GraphNode) WHERE n.id = $id SET n.is_dead = true",
                {"id": nid},
            )

    def get_all_symbol_nodes(self) -> list[GraphNode]:
        """Return all FUNCTION, CLASS, METHOD, ENUM nodes."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.label IN ['function', 'class', 'method', 'enum'] RETURN n.*"
        )
        nodes: list[GraphNode] = []
        while result.has_next():
            nodes.append(_row_to_node(result.get_next()))
        return nodes

    def get_dead_nodes(self) -> list[GraphNode]:
        """Return all nodes where is_dead=True."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.is_dead = true RETURN n.*"
        )
        nodes: list[GraphNode] = []
        while result.has_next():
            nodes.append(_row_to_node(result.get_next()))
        return nodes

    # ------------------------------------------------------------------
    # Relationship operations
    # ------------------------------------------------------------------

    def add_relationships(self, rels: list[GraphRelationship]) -> None:
        """Create relationships.  Callers must deduplicate before calling — duplicates will be inserted."""
        if not rels:
            return
        conn = self._require_conn()
        for rel in rels:
            confidence = rel.properties.get("confidence", 1.0)
            props_str = json.dumps(rel.properties)
            conn.execute(
                """
                MATCH (a:GraphNode), (b:GraphNode)
                WHERE a.id = $src AND b.id = $tgt
                CREATE (a)-[:CodeRelation {
                    rel_id: $rid,
                    rel_type: $rtype,
                    confidence: $conf,
                    properties: $props
                }]->(b)
                """,
                {
                    "src": rel.source,
                    "tgt": rel.target,
                    "rid": rel.id,
                    "rtype": rel.type.value,
                    "conf": float(confidence),
                    "props": props_str,
                },
            )

    def get_related_nodes(
        self, node_id: str, rel_type: RelType, direction: str
    ) -> list[GraphNode]:
        """Return nodes connected to node_id by rel_type.

        direction: ``"outgoing"`` (node_id -> other) or ``"incoming"`` (other -> node_id).
        """
        conn = self._require_conn()
        if direction == "outgoing":
            result = conn.execute(
                """
                MATCH (src:GraphNode)-[r:CodeRelation]->(tgt:GraphNode)
                WHERE src.id = $id AND r.rel_type = $rtype
                RETURN tgt.*
                """,
                {"id": node_id, "rtype": rel_type.value},
            )
        else:
            result = conn.execute(
                """
                MATCH (src:GraphNode)-[r:CodeRelation]->(tgt:GraphNode)
                WHERE tgt.id = $id AND r.rel_type = $rtype
                RETURN src.*
                """,
                {"id": node_id, "rtype": rel_type.value},
            )
        nodes: list[GraphNode] = []
        while result.has_next():
            nodes.append(_row_to_node(result.get_next()))
        return nodes

    def get_callers_with_confidence(
        self, node_id: str
    ) -> list[tuple[GraphNode, float]]:
        """Return (caller_node, confidence) for all CALLS incoming edges."""
        conn = self._require_conn()
        result = conn.execute(
            """
            MATCH (caller:GraphNode)-[r:CodeRelation]->(callee:GraphNode)
            WHERE callee.id = $id AND r.rel_type = 'calls'
            RETURN caller.*, r.confidence
            """,
            {"id": node_id},
        )
        out: list[tuple[GraphNode, float]] = []
        while result.has_next():
            row = result.get_next()
            node = _row_to_node(row[:-1])
            conf = float(row[-1]) if row[-1] is not None else 1.0
            out.append((node, conf))
        return out

    def get_callees(self, node_id: str) -> list[GraphNode]:
        """Return nodes that node_id calls (outgoing CALLS edges)."""
        return self.get_related_nodes(node_id, RelType.CALLS, "outgoing")

    def get_all_relationships_by_types(
        self, rel_types: list[str]
    ) -> list[tuple[str, str, str]]:
        """Return all (source_id, target_id, rel_type) for the given rel_type strings."""
        if not rel_types:
            return []
        conn = self._require_conn()
        params = {f"t{i}": t for i, t in enumerate(rel_types)}
        placeholders = ", ".join(f"$t{i}" for i in range(len(rel_types)))
        result = conn.execute(
            f"MATCH (a:GraphNode)-[r:CodeRelation]->(b:GraphNode) "
            f"WHERE r.rel_type IN [{placeholders}] "
            f"RETURN a.id, b.id, r.rel_type",
            params,
        )
        rows: list[tuple[str, str, str]] = []
        while result.has_next():
            row = result.get_next()
            rows.append((row[0], row[1], row[2]))
        return rows

    # ------------------------------------------------------------------
    # File hash tracking (incremental indexing)
    # ------------------------------------------------------------------

    def get_indexed_files(self) -> dict[str, str]:
        """Return mapping of file_path -> content_hash for all indexed files."""
        conn = self._require_conn()
        result = conn.execute("MATCH (h:FileHash) RETURN h.file_path, h.content_hash")
        out: dict[str, str] = {}
        while result.has_next():
            row = result.get_next()
            out[row[0]] = row[1]
        return out

    def update_file_hash(self, file_path: str, content_hash: str) -> None:
        """Upsert content hash for a file."""
        conn = self._require_conn()
        conn.execute(
            "MERGE (h:FileHash {file_path: $fp}) SET h.content_hash = $ch",
            {"fp": file_path, "ch": content_hash},
        )

    def remove_file_hash(self, file_path: str) -> None:
        """Delete the file hash entry for file_path."""
        conn = self._require_conn()
        conn.execute(
            "MATCH (h:FileHash) WHERE h.file_path = $fp DELETE h",
            {"fp": file_path},
        )

    # ------------------------------------------------------------------
    # Reverse dependency & edge management
    # ------------------------------------------------------------------

    def get_reverse_dependency_files(self, file_paths: list[str]) -> list[str]:
        """Return distinct file paths that have outgoing edges into nodes in file_paths.

        Used during incremental reindex to find unchanged files whose edges
        into changed files need rebuilding.
        """
        if not file_paths:
            return []
        conn = self._require_conn()
        params = {f"f{i}": fp for i, fp in enumerate(file_paths)}
        placeholders = ", ".join(f"$f{i}" for i in range(len(file_paths)))
        result = conn.execute(
            f"MATCH (n:GraphNode)-[r:CodeRelation]->(m:GraphNode) "
            f"WHERE m.file_path IN [{placeholders}] AND NOT n.file_path IN [{placeholders}] "
            f"RETURN DISTINCT n.file_path",
            params,
        )
        paths: list[str] = []
        while result.has_next():
            row = result.get_next()
            if row[0]:
                paths.append(row[0])
        return paths

    def remove_edges_from_file(self, file_path: str) -> None:
        """Delete all outgoing edges from nodes in file_path (preserves nodes)."""
        conn = self._require_conn()
        conn.execute(
            """
            MATCH (n:GraphNode)-[r:CodeRelation]->()
            WHERE n.file_path = $fp DELETE r
            """,
            {"fp": file_path},
        )

    def remove_edges_from_file_by_types(
        self, file_path: str, rel_types: list[str]
    ) -> None:
        """Delete outgoing edges of specific types from nodes in file_path."""
        if not rel_types:
            return
        conn = self._require_conn()
        params: dict[str, str] = {"fp": file_path}
        params.update({f"t{i}": t for i, t in enumerate(rel_types)})
        placeholders = ", ".join(f"$t{i}" for i in range(len(rel_types)))
        conn.execute(
            f"MATCH (n:GraphNode)-[r:CodeRelation]->() "
            f"WHERE n.file_path = $fp AND r.rel_type IN [{placeholders}] DELETE r",
            params,
        )

    # ------------------------------------------------------------------
    # Remove by file
    # ------------------------------------------------------------------

    def remove_nodes_by_file(self, file_path: str) -> None:
        """Delete all nodes for file_path and their relationships."""
        conn = self._require_conn()
        # Delete outgoing and incoming relationships first
        conn.execute(
            """
            MATCH (n:GraphNode)-[r:CodeRelation]->()
            WHERE n.file_path = $fp DELETE r
            """,
            {"fp": file_path},
        )
        conn.execute(
            """
            MATCH ()-[r:CodeRelation]->(n:GraphNode)
            WHERE n.file_path = $fp DELETE r
            """,
            {"fp": file_path},
        )
        # Delete the nodes
        conn.execute(
            "MATCH (n:GraphNode) WHERE n.file_path = $fp DELETE n",
            {"fp": file_path},
        )

    # ------------------------------------------------------------------
    # Full-text search (CONTAINS-based with scoring)
    # ------------------------------------------------------------------

    def rebuild_fts(self) -> None:
        """Rebuild search index.  No-op for CONTAINS-based search."""
        # CONTAINS-based search reads live data; nothing to pre-build.

    def search(self, query: str, limit: int = 20) -> list[tuple[GraphNode, float]]:
        """Search nodes by name, signature, and content using CONTAINS.

        Returns (node, score) tuples sorted by relevance (higher = better).
        Score is the count of fields that contain the query string.
        """
        conn = self._require_conn()
        q_lower = query.lower()
        result = conn.execute(
            """
            MATCH (n:GraphNode)
            WHERE lower(n.name) CONTAINS $q
               OR lower(n.signature) CONTAINS $q
               OR lower(n.content) CONTAINS $q
            RETURN n.*
            """,
            {"q": q_lower},
        )
        scored: list[tuple[GraphNode, float]] = []
        while result.has_next():
            row = result.get_next()
            node = _row_to_node(row)
            score = (
                (1.0 if q_lower in (node.name or "").lower() else 0.0)
                + (0.5 if q_lower in (node.signature or "").lower() else 0.0)
                + (0.3 if q_lower in (node.content or "").lower() else 0.0)
            )
            scored.append((node, score))
        # Sort by descending score, then by name for stable ordering
        scored.sort(key=lambda t: (-t[1], t[0].name))
        return scored[:limit]

    # ------------------------------------------------------------------
    # Retrieve all nodes
    # ------------------------------------------------------------------

    def get_all_nodes(self) -> list[GraphNode]:
        """Return every GraphNode in the graph."""
        conn = self._require_conn()
        result = conn.execute("MATCH (n:GraphNode) RETURN n.*")
        nodes: list[GraphNode] = []
        while result.has_next():
            nodes.append(_row_to_node(result.get_next()))
        return nodes

    def get_symbol_nodes_by_file(self, file_path: str) -> list[tuple[str, str, str]]:
        """Return (id, name, class_name) for function/class/method nodes in file_path."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.file_path = $fp AND n.label IN ['function', 'class', 'method'] "
            "RETURN n.id, n.name, n.class_name",
            {"fp": file_path},
        )
        rows: list[tuple[str, str, str]] = []
        while result.has_next():
            row = result.get_next()
            rows.append((row[0], row[1], row[2] or ""))
        return rows

    def get_all_file_paths(self) -> list[str]:
        """Return file_path for all FILE-label nodes."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.label = 'file' RETURN n.file_path"
        )
        paths: list[str] = []
        while result.has_next():
            row = result.get_next()
            if row[0]:
                paths.append(row[0])
        return paths

    def get_all_callable_nodes(self) -> list[tuple[str, str, str, str, str]]:
        """Return (id, name, class_name, label, file_path) for function/method/class nodes."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.label IN ['function', 'method', 'class'] "
            "RETURN n.id, n.name, n.class_name, n.label, n.file_path"
        )
        rows: list[tuple[str, str, str, str, str]] = []
        while result.has_next():
            row = result.get_next()
            rows.append((row[0], row[1], row[2] or "", row[3], row[4] or ""))
        return rows

    def get_class_like_nodes(self) -> list[tuple[str, str]]:
        """Return (id, name) for class/interface/type_alias/enum nodes."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.label IN ['class', 'interface', 'type_alias', 'enum'] RETURN n.id, n.name"
        )
        rows: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            rows.append((row[0], row[1]))
        return rows

    def get_type_nodes(self) -> list[tuple[str, str]]:
        """Return (id, name) for class/interface/type_alias/enum nodes."""
        conn = self._require_conn()
        result = conn.execute(
            "MATCH (n:GraphNode) WHERE n.label IN ['class', 'interface', 'type_alias', 'enum'] RETURN n.id, n.name"
        )
        rows: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            rows.append((row[0], row[1]))
        return rows

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_conn(self) -> kuzu.Connection:
        if self._conn is None:
            raise RuntimeError("GraphStorage not initialized — call initialize() first")
        return self._conn
