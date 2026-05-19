"""Support-graph extraction.

Given an attribution graph and a success certificate, extract the subgraph of
trajectory atoms that supports the certificate's outcome atoms. This is the
supervision signal for the context policy.
"""

from __future__ import annotations

from ablation.base import SuccessCertificate
from core.graph import AttributionEdge, AttributionGraph, SupportGraph


def _trajectory_edges(edges: list[AttributionEdge], keep: set[str]) -> list[AttributionEdge]:
    """Edges whose source is a retained trajectory atom."""
    return [e for e in edges if e.source_atom_id in keep]


def extract_topk_support(
    graph: AttributionGraph,
    certificate: SuccessCertificate,
    k_per_outcome: int = 5,
) -> SupportGraph:
    """Keep the top-`k` weighted trajectory atoms feeding each certificate atom.

    Then transitively pull in their upstream atoms so the support graph is
    closed under the "contributed to" relation.
    """
    targets = list(certificate.outcome_atom_ids)
    direct: set[str] = set()
    chosen_edges: list[AttributionEdge] = []
    for target in targets:
        incoming = sorted(graph.incoming_edges(target), key=lambda e: -e.weight)[:k_per_outcome]
        for edge in incoming:
            direct.add(edge.source_atom_id)
            chosen_edges.append(edge)

    upstream = graph.upstream_atoms(sorted(direct))
    keep = direct | upstream
    all_support_edges = chosen_edges + _trajectory_edges(graph.edges, keep)
    # De-dup edges.
    seen: set[tuple[str, str, float]] = set()
    edges: list[AttributionEdge] = []
    for e in all_support_edges:
        key = (e.source_atom_id, e.target_atom_id, e.weight)
        if key not in seen:
            seen.add(key)
            edges.append(e)

    return SupportGraph(
        atom_ids=sorted(keep),
        edges=edges,
        certificate_id=certificate.task_id,
        metadata={"method": "topk", "k_per_outcome": k_per_outcome},
    )


def extract_threshold_support(
    graph: AttributionGraph,
    certificate: SuccessCertificate,
    threshold: float = 0.5,
) -> SupportGraph:
    """Keep every trajectory atom feeding a certificate atom with weight >= t.

    Then close transitively over edges at or above the same threshold.
    """
    targets = set(certificate.outcome_atom_ids)
    direct: set[str] = set()
    chosen_edges: list[AttributionEdge] = []
    for edge in graph.edges:
        if edge.target_atom_id in targets and edge.weight >= threshold:
            direct.add(edge.source_atom_id)
            chosen_edges.append(edge)

    upstream = graph.upstream_atoms(sorted(direct), min_weight=threshold)
    keep = direct | upstream
    edges = chosen_edges + [
        e for e in graph.edges if e.source_atom_id in keep and e.weight >= threshold
    ]
    seen: set[tuple[str, str, float]] = set()
    uniq: list[AttributionEdge] = []
    for e in edges:
        key = (e.source_atom_id, e.target_atom_id, e.weight)
        if key not in seen:
            seen.add(key)
            uniq.append(e)

    return SupportGraph(
        atom_ids=sorted(keep),
        edges=uniq,
        certificate_id=certificate.task_id,
        metadata={"method": "threshold", "threshold": threshold},
    )
