"""Semantic embedding engine using sentence-transformers (BAAI/bge-small-en-v1.5)."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from scripts.context.model import GraphNode
from scripts.context.storage import GraphStorage


# Model config
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_EMBEDDING_DIM = 384
_CACHE_DIR = Path.home() / ".cache" / "cnogo" / "models"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingEngine:
    """Semantic embedding engine using BAAI/bge-small-en-v1.5.

    384-dimensional vectors. Lazy model loading — model is not loaded until
    first embed call. Model is cached at ~/.cache/cnogo/models/.
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else _CACHE_DIR
        self._model: Any = None  # SentenceTransformer instance, lazy loaded

    def _ensure_model(self) -> Any:
        """Load model on first use (lazy initialization)."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = SentenceTransformer(_MODEL_NAME, cache_folder=str(self._cache_dir))
        return self._model

    @property
    def dimension(self) -> int:
        """Return the embedding dimension (384 for bge-small-en-v1.5)."""
        return _EMBEDDING_DIM

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string. Returns 384-dim vector."""
        model = self._ensure_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Returns list of 384-dim vectors."""
        if not texts:
            return []
        model = self._ensure_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]

    def embed_nodes(self, nodes: list[GraphNode], max_content_lines: int = 10) -> list[list[float]]:
        """Embed graph nodes using name + signature + content snippet.

        For each node, combines:
        - name
        - signature (if present)
        - first N lines of content

        Returns list of embedding vectors, one per node.
        """
        texts = []
        for node in nodes:
            parts = [node.name]
            if node.signature:
                parts.append(node.signature)
            if node.content:
                lines = node.content.split("\n")[:max_content_lines]
                parts.append("\n".join(lines))
            texts.append(" ".join(parts))

        return self.embed_batch(texts)
