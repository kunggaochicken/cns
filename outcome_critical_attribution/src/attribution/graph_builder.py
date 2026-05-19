"""Helpers for assembling attribution graphs.

Includes a dependency-free `HeuristicAttributor` based on lexical overlap,
which lets the whole pipeline run end-to-end without any LLM. It is also a
reasonable attribution *prior* (the `p_phi` in the policy training loss).
"""

from __future__ import annotations

import math
import re
from collections import Counter

from core.atoms import Atom, OutcomeAtom
from core.graph import AttributionEdge, AttributionGraph

_WORD = re.compile(r"[a-z0-9_]+")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "or",
    "is",
    "are",
    "be",
    "in",
    "on",
    "for",
    "with",
    "that",
    "this",
    "it",
    "as",
    "at",
    "by",
    "we",
    "i",
    "you",
}


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOPWORDS]


def _vector(text: str) -> Counter:
    return Counter(tokenize(text))


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def build_graph(
    trajectory_atoms: list[Atom],
    outcome_atoms: list[OutcomeAtom],
    edges: list[AttributionEdge],
) -> AttributionGraph:
    """Assemble an AttributionGraph from explicit edges and an atom pool."""
    atoms: dict[str, Atom] = {a.id: a for a in trajectory_atoms}
    atoms.update({a.id: a for a in outcome_atoms})
    return AttributionGraph(atoms=atoms, edges=edges)


class HeuristicAttributor:
    """Lexical-overlap attributor (implements the AttributionModel protocol).

    Draws an edge from a trajectory atom to an outcome atom when their
    bag-of-words cosine similarity exceeds `min_weight`. No LLM required.
    """

    def __init__(self, min_weight: float = 0.15, max_edges_per_outcome: int = 8):
        self.min_weight = min_weight
        self.max_edges_per_outcome = max_edges_per_outcome

    def attribute(
        self,
        trajectory_atoms: list[Atom],
        outcome_atoms: list[OutcomeAtom],
    ) -> AttributionGraph:
        traj_vectors = [(a, _vector(a.content)) for a in trajectory_atoms]
        edges: list[AttributionEdge] = []
        for oatom in outcome_atoms:
            ovec = _vector(oatom.content)
            scored = []
            for atom, tvec in traj_vectors:
                w = cosine(tvec, ovec)
                if w >= self.min_weight:
                    scored.append((atom, w))
            scored.sort(key=lambda x: -x[1])
            for atom, w in scored[: self.max_edges_per_outcome]:
                edges.append(
                    AttributionEdge(
                        source_atom_id=atom.id,
                        target_atom_id=oatom.id,
                        weight=round(w, 4),
                        method="heuristic_cosine",
                        evidence=f"lexical overlap cosine={w:.3f}",
                    )
                )
        return build_graph(trajectory_atoms, outcome_atoms, edges)
