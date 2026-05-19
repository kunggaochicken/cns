"""Context-policy models.

`ContextPolicy` is the general interface. Two implementations:

* `HeuristicPolicy` -- a zero-training baseline that scores atoms by their
  attribution-prior soft label (or a feature blend).
* `LogisticContextPolicy` -- a dependency-free logistic-regression model over
  hand-built atom features, trainable with plain gradient descent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from core.atoms import Atom

# Trajectory atom types, used for a one-hot feature block.
_FEATURE_ATOM_TYPES = [
    "instruction",
    "constraint",
    "observation",
    "tool_input",
    "tool_output",
    "memory",
    "plan",
    "decision",
    "intermediate_result",
    "environment_fact",
    "artifact_atom",
    "final_response_atom",
]


@runtime_checkable
class ContextPolicy(Protocol):
    """Scores trajectory atoms and selects which to retain."""

    def score_atoms(self, atoms: list[Atom]) -> list[float]: ...

    def select_atoms(
        self,
        atoms: list[Atom],
        budget_tokens: int | None = None,
        threshold: float | None = None,
    ) -> list[Atom]: ...


def _select_by_scores(
    atoms: list[Atom],
    scores: list[float],
    budget_tokens: int | None,
    threshold: float | None,
) -> list[Atom]:
    """Shared selection logic: threshold filter and/or token budget."""
    ranked = sorted(zip(atoms, scores, strict=True), key=lambda x: -x[1])
    selected: list[Atom] = []
    used = 0
    for atom, score in ranked:
        if threshold is not None and score < threshold:
            continue
        if budget_tokens is not None and used + atom.token_count > budget_tokens:
            continue
        selected.append(atom)
        used += atom.token_count
    if threshold is None and budget_tokens is None:
        # No constraint given: keep the better-than-median half.
        if not ranked:
            return []
        mid = ranked[len(ranked) // 2][1]
        return [a for a, s in zip(atoms, scores, strict=True) if s >= mid]
    # Preserve original trajectory order in the output.
    keep = {id(a) for a in selected}
    return [a for a in atoms if id(a) in keep]


def featurize(atom: Atom, position: float, max_tokens: int) -> list[float]:
    """Hand-built feature vector for one trajectory atom.

    Features: bias, normalized token count, position in trajectory, atom-type
    one-hot, and an attribution-prior value if the atom carries one in
    `metadata["attribution_prior"]`.
    """
    feats = [1.0]
    feats.append(atom.token_count / max(1, max_tokens))
    feats.append(position)
    feats.extend(1.0 if atom.atom_type == t else 0.0 for t in _FEATURE_ATOM_TYPES)
    feats.append(float(atom.metadata.get("attribution_prior", 0.0)))
    return feats


FEATURE_DIM = 1 + 1 + 1 + len(_FEATURE_ATOM_TYPES) + 1


def _sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class HeuristicPolicy:
    """Zero-training policy: score = attribution prior on each atom.

    Reads `metadata["attribution_prior"]` (set by the pipeline). Falls back to
    a recency score when no prior is present.
    """

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        n = max(1, len(atoms))
        scores = []
        for i, a in enumerate(atoms):
            prior = a.metadata.get("attribution_prior")
            scores.append(float(prior) if prior is not None else (i + 1) / n)
        return scores

    def select_atoms(
        self,
        atoms: list[Atom],
        budget_tokens: int | None = None,
        threshold: float | None = None,
    ) -> list[Atom]:
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class LogisticContextPolicy:
    """Logistic regression over `featurize` features. Pure-Python, no deps."""

    weights: list[float] = field(default_factory=lambda: [0.0] * FEATURE_DIM)
    max_tokens: int = 64

    def _features(self, atoms: list[Atom]) -> list[list[float]]:
        n = max(1, len(atoms))
        return [featurize(a, i / n, self.max_tokens) for i, a in enumerate(atoms)]

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        scores = []
        for feats in self._features(atoms):
            z = sum(w * f for w, f in zip(self.weights, feats, strict=True))
            scores.append(_sigmoid(z))
        return scores

    def select_atoms(
        self,
        atoms: list[Atom],
        budget_tokens: int | None = None,
        threshold: float | None = None,
    ) -> list[Atom]:
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)
