"""Search engines for the context graph: BM25 full-text and fuzzy matching."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from scripts.context.embeddings import EmbeddingEngine, cosine_similarity
from scripts.context.model import GraphNode, NodeLabel
from scripts.context.storage import GraphStorage


@dataclass
class SearchResult:
    """A single search result with provenance."""
    node_id: str
    name: str
    score: float
    source: str  # "bm25", "fuzzy", "semantic", or "hybrid"


class BM25Search:
    """BM25 full-text search over symbol nodes.

    Indexes symbol names, signatures, and content (first 500 chars).
    Uses rank-bm25 BM25Okapi for scoring.
    """

    def __init__(self) -> None:
        self._corpus: list[list[str]] = []  # tokenized documents
        self._node_map: list[GraphNode] = []  # parallel array of nodes
        self._bm25: BM25Okapi | None = None

    def build_index(self, storage: GraphStorage) -> None:
        """Build BM25 index from all symbol nodes in storage."""
        nodes = storage.get_all_symbol_nodes()
        self._corpus = []
        self._node_map = []

        for node in nodes:
            # Combine name + signature + content snippet as document
            text = f"{node.name} {node.signature} {node.content[:500]}"
            tokens = self._tokenize(text)
            self._corpus.append(tokens)
            self._node_map.append(node)

        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search for nodes matching query. Returns SearchResult list sorted by score desc."""
        if not self._bm25 or not self._corpus:
            return []

        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)

        # Pair (score, node), filter zeros, sort desc
        scored = [(scores[i], self._node_map[i]) for i in range(len(scores)) if scores[i] > 0]
        scored.sort(key=lambda x: -x[0])

        results = []
        for score, node in scored[:limit]:
            results.append(SearchResult(
                node_id=node.id,
                name=node.name,
                score=float(score),
                source="bm25",
            ))
        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + lowercase tokenization."""
        return text.lower().split()


class FuzzySearch:
    """Fuzzy string matching search on symbol names.

    Uses difflib.SequenceMatcher for approximate matching.
    """

    def __init__(self, threshold: float = 0.4) -> None:
        self._threshold = threshold
        self._nodes: list[GraphNode] = []

    def build_index(self, storage: GraphStorage) -> None:
        """Load all symbol nodes for fuzzy matching."""
        self._nodes = storage.get_all_symbol_nodes()

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Fuzzy search symbol names. Returns SearchResult list sorted by score desc."""
        import difflib

        if not self._nodes:
            return []

        query_lower = query.lower()
        scored: list[tuple[float, GraphNode]] = []

        for node in self._nodes:
            # Match against node name
            ratio = difflib.SequenceMatcher(None, query_lower, node.name.lower()).ratio()
            if ratio >= self._threshold:
                scored.append((ratio, node))

        scored.sort(key=lambda x: -x[0])

        results = []
        for score, node in scored[:limit]:
            results.append(SearchResult(
                node_id=node.id,
                name=node.name,
                score=float(score),
                source="fuzzy",
            ))
        return results


class HybridSearch:
    """Hybrid search combining BM25, semantic, and fuzzy search via Reciprocal Rank Fusion.

    RRF score = sum(1/(k + rank_i)) across all rankers where k=60.
    """

    def __init__(
        self,
        bm25: BM25Search | None = None,
        embedding_engine: EmbeddingEngine | None = None,
        fuzzy: FuzzySearch | None = None,
        k: int = 60,
    ) -> None:
        self._bm25 = bm25 or BM25Search()
        self._embedding = embedding_engine
        self._fuzzy = fuzzy or FuzzySearch()
        self._k = k
        self._node_embeddings: dict[str, list[float]] = {}  # node_id -> embedding
        self._node_map: dict[str, GraphNode] = {}  # node_id -> node

    def build_index(self, storage: GraphStorage) -> None:
        """Build indices for all search components and store embeddings."""
        self._bm25.build_index(storage)
        self._fuzzy.build_index(storage)

        # Build embedding index if engine available
        if self._embedding is not None:
            nodes = storage.get_all_symbol_nodes()
            if nodes:
                vectors = self._embedding.embed_nodes(nodes)
                for node, vec in zip(nodes, vectors):
                    self._node_embeddings[node.id] = vec
                    self._node_map[node.id] = node

    def _semantic_search(self, query: str, limit: int) -> list[SearchResult]:
        """Run semantic search using embeddings."""
        if not self._embedding or not self._node_embeddings:
            return []

        query_vec = self._embedding.embed_text(query)
        scored: list[tuple[float, str]] = []

        for node_id, node_vec in self._node_embeddings.items():
            sim = cosine_similarity(query_vec, node_vec)
            if sim > 0:
                scored.append((sim, node_id))

        scored.sort(key=lambda x: -x[0])

        results = []
        for score, node_id in scored[:limit]:
            node = self._node_map[node_id]
            results.append(SearchResult(
                node_id=node_id,
                name=node.name,
                score=float(score),
                source="semantic",
            ))
        return results

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Run hybrid search: BM25 + semantic + fuzzy, fused via RRF.

        Returns SearchResult list sorted by fused RRF score descending.
        Each result has source="hybrid".
        """
        # Get results from each ranker
        bm25_results = self._bm25.search(query, limit=limit * 2)
        fuzzy_results = self._fuzzy.search(query, limit=limit * 2)
        semantic_results = self._semantic_search(query, limit=limit * 2)

        # Compute RRF scores
        rrf_scores: dict[str, float] = {}
        node_names: dict[str, str] = {}

        for rank, r in enumerate(bm25_results):
            rrf_scores[r.node_id] = rrf_scores.get(r.node_id, 0.0) + 1.0 / (self._k + rank + 1)
            node_names[r.node_id] = r.name

        for rank, r in enumerate(fuzzy_results):
            rrf_scores[r.node_id] = rrf_scores.get(r.node_id, 0.0) + 1.0 / (self._k + rank + 1)
            node_names[r.node_id] = r.name

        for rank, r in enumerate(semantic_results):
            rrf_scores[r.node_id] = rrf_scores.get(r.node_id, 0.0) + 1.0 / (self._k + rank + 1)
            node_names[r.node_id] = r.name

        # Sort by RRF score descending
        sorted_ids = sorted(rrf_scores.keys(), key=lambda nid: -rrf_scores[nid])

        results = []
        for node_id in sorted_ids[:limit]:
            results.append(SearchResult(
                node_id=node_id,
                name=node_names[node_id],
                score=rrf_scores[node_id],
                source="hybrid",
            ))
        return results
