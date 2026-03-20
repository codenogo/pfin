"""Coupling analysis phase using Jaccard similarity of shared neighbors.

Identifies structurally coupled symbol pairs by computing the Jaccard
similarity of their neighbor sets (callers + callees + importers + imports)
from the code graph. Pairs above a threshold get COUPLED_WITH relationships.
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.context.model import (
    GraphNode,
    GraphRelationship,
    NodeLabel,
    RelType,
)
from scripts.context.storage import GraphStorage

# Edge types used to build neighbor sets
_NEIGHBOR_EDGE_TYPES = [RelType.CALLS.value, RelType.IMPORTS.value]

# Symbol node labels considered for coupling analysis
_SYMBOL_LABELS = {NodeLabel.FUNCTION.value, NodeLabel.CLASS.value, NodeLabel.METHOD.value}


@dataclass
class CouplingResult:
    """A single coupling pair result."""

    source_id: str
    source_name: str
    target_id: str
    target_name: str
    strength: float    # Jaccard similarity of shared neighbors
    shared_count: int  # number of shared neighbors


def _query_symbol_nodes(storage: GraphStorage) -> list[tuple[str, str]]:
    """Return (node_id, name) for all function/class/method nodes."""
    rows = storage.get_all_callable_nodes()
    return [(nid, name) for nid, name, _cn, _lbl, _fp in rows
            if _lbl in _SYMBOL_LABELS]


def _build_neighbor_sets(
    storage: GraphStorage, node_ids: list[str]
) -> dict[str, set[str]]:
    """Build neighbor sets for each node_id using CALLS and IMPORTS edges."""
    # Fetch all relevant edges at once
    edges = storage.get_all_relationships_by_types(_NEIGHBOR_EDGE_TYPES)

    node_id_set = set(node_ids)

    # For each symbol node, collect both incoming and outgoing neighbors
    neighbors: dict[str, set[str]] = {nid: set() for nid in node_ids}

    for src, tgt, _rtype in edges:
        if src in node_id_set:
            neighbors[src].add(tgt)
        if tgt in node_id_set:
            neighbors[tgt].add(src)

    return neighbors


def _build_candidate_pairs(
    neighbor_sets: dict[str, set[str]],
) -> set[tuple[str, str]]:
    """Return candidate symbol pairs that share at least one neighbor.

    Builds an inverted index (neighbor -> set of symbol_ids) and collects
    pairs from co-occurrence in posting lists. Returns canonically ordered
    (a_id, b_id) tuples where a_id < b_id.
    """
    # Inverted index: neighbor_id -> set of symbol_ids that have it as neighbor
    inv: dict[str, list[str]] = {}
    for sym_id, neighbors in neighbor_sets.items():
        for nb in neighbors:
            inv.setdefault(nb, []).append(sym_id)

    # Generate candidate pairs from co-occurrence
    candidates: set[tuple[str, str]] = set()
    for symbols in inv.values():
        n = len(symbols)
        if n < 2:
            continue
        for i in range(n):
            for j in range(i + 1, n):
                a, b = symbols[i], symbols[j]
                # Canonical ordering
                if a > b:
                    a, b = b, a
                candidates.add((a, b))

    return candidates


def compute_coupling(
    storage: GraphStorage,
    threshold: float = 0.1,
) -> list[CouplingResult]:
    """Compute structural coupling between symbol pairs using Jaccard similarity.

    1. Query all symbol nodes (function, class, method).
    2. For each pair, compute Jaccard similarity of their neighbor sets.
    3. Create COUPLED_WITH relationships for pairs above threshold.
    4. Return list of CouplingResult sorted by strength descending.
    """
    symbol_nodes = _query_symbol_nodes(storage)

    if len(symbol_nodes) < 2:
        return []

    node_ids = [nid for nid, _name in symbol_nodes]
    name_map = {nid: name for nid, name in symbol_nodes}

    neighbor_sets = _build_neighbor_sets(storage, node_ids)

    results: list[CouplingResult] = []
    coupled_rels: list[GraphRelationship] = []

    # Only evaluate pairs that share at least one neighbor (inverted-index pruning)
    candidate_pairs = _build_candidate_pairs(neighbor_sets)

    for a_id, b_id in candidate_pairs:
        nb_a = neighbor_sets[a_id]
        nb_b = neighbor_sets[b_id]

        intersection = nb_a & nb_b
        union = nb_a | nb_b

        if not union or not intersection:
            continue

        jaccard = len(intersection) / len(union)
        shared = len(intersection)

        if jaccard < threshold:
            continue

        a_name = name_map[a_id]
        b_name = name_map[b_id]

        results.append(CouplingResult(
            source_id=a_id,
            source_name=a_name,
            target_id=b_id,
            target_name=b_name,
            strength=jaccard,
            shared_count=shared,
        ))

        coupled_rels.append(GraphRelationship(
            id=f"coupled:{a_id}->{b_id}",
            type=RelType.COUPLED_WITH,
            source=a_id,
            target=b_id,
            properties={
                "structural_score": jaccard,
                "temporal_score": 0.0,
                "combined_score": jaccard,
                "shared_count": shared,
            },
        ))

    if coupled_rels:
        storage.add_relationships(coupled_rels)

    results.sort(key=lambda r: -r.strength)
    return results
