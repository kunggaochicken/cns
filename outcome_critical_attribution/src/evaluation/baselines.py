"""Baseline context-selection policies.

Every baseline implements the `ContextPolicy` interface (score + select) so the
benchmark can treat the learned policy and the baselines uniformly. They cover
the comparison set from the thesis: random, recency, lexical/embedding/BM25
similarity to the outcome, LLM summary/ranking stubs, and the
attribution-only / ablation-only oracles.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

from attribution.graph_builder import cosine, tokenize
from core.atoms import Atom, OutcomeAtom
from policy.model import _select_by_scores


@dataclass
class RandomPolicy:
    """Selects atoms uniformly at random (seeded for reproducibility)."""

    seed: int = 0

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        rng = random.Random(self.seed)
        return [rng.random() for _ in atoms]

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class RecencyPolicy:
    """Prefers the most recent atoms (later trajectory position scores higher)."""

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        n = max(1, len(atoms))
        return [(i + 1) / n for i in range(len(atoms))]

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class TokenOverlapPolicy:
    """Scores atoms by raw token overlap with the final outcome text."""

    outcome_atoms: list[OutcomeAtom] = field(default_factory=list)

    def _outcome_tokens(self) -> Counter:
        c: Counter = Counter()
        for a in self.outcome_atoms:
            c.update(tokenize(a.content))
        return c

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        out = self._outcome_tokens()
        scores = []
        for a in atoms:
            toks = tokenize(a.content)
            overlap = sum(1 for t in toks if t in out)
            scores.append(overlap / max(1, len(toks)))
        return scores

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class EmbeddingSimilarityPolicy:
    """Bag-of-words cosine similarity to the outcome (a stand-in embedding)."""

    outcome_atoms: list[OutcomeAtom] = field(default_factory=list)

    def _outcome_vec(self) -> Counter:
        c: Counter = Counter()
        for a in self.outcome_atoms:
            c.update(tokenize(a.content))
        return c

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        ovec = self._outcome_vec()
        return [cosine(Counter(tokenize(a.content)), ovec) for a in atoms]

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class BM25Policy:
    """BM25 relevance of each atom to the final-outcome query."""

    outcome_atoms: list[OutcomeAtom] = field(default_factory=list)
    k1: float = 1.5
    b: float = 0.75

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        docs = [tokenize(a.content) for a in atoms]
        n = len(docs)
        if n == 0:
            return []
        avgdl = sum(len(d) for d in docs) / n or 1.0
        df: Counter = Counter()
        for d in docs:
            for t in set(d):
                df[t] += 1
        query: list[str] = []
        for a in self.outcome_atoms:
            query.extend(tokenize(a.content))
        query_terms = set(query)

        scores = []
        for d in docs:
            tf = Counter(d)
            dl = len(d) or 1
            s = 0.0
            for t in query_terms:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                numer = tf[t] * (self.k1 + 1)
                denom = tf[t] + self.k1 * (1 - self.b + self.b * dl / avgdl)
                s += idf * numer / denom
            scores.append(s)
        # Normalize to [0, 1] for uniform thresholding.
        hi = max(scores) or 1.0
        return [s / hi for s in scores]

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class LLMSummaryPolicy:
    """LLM-summary baseline.

    A summarizer keeps semantically central atoms. With no LLM wired in, we
    approximate "central" as similarity to the *trajectory centroid* -- which,
    crucially, is NOT the success-conditioned signal this framework targets.
    """

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        centroid: Counter = Counter()
        for a in atoms:
            centroid.update(tokenize(a.content))
        return [cosine(Counter(tokenize(a.content)), centroid) for a in atoms]

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class LLMImportanceRankingPolicy:
    """LLM importance-ranking baseline.

    Approximated by a length-and-type heuristic: longer atoms and decisions /
    plans / tool outputs are ranked "more important". Generic, outcome-blind.
    """

    _IMPORTANT = {"plan", "decision", "tool_output", "intermediate_result"}

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        max_tok = max((a.token_count for a in atoms), default=1) or 1
        scores = []
        for a in atoms:
            base = a.token_count / max_tok
            bonus = 0.3 if a.atom_type in self._IMPORTANT else 0.0
            scores.append(min(1.0, base + bonus))
        return scores

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class AttributionOnlyPolicy:
    """Selects atoms purely by attribution-prior weight (no outcome ablation).

    Uses every attribution edge into *any* outcome atom -- it never asks which
    outcome atoms actually mattered.
    """

    atom_scores: dict[str, float] = field(default_factory=dict)

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        return [self.atom_scores.get(a.id, 0.0) for a in atoms]

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)


@dataclass
class AblationOnlyPolicy:
    """Selects atoms that lexically match a *certificate* outcome atom.

    Uses outcome ablation but no graph traversal -- a useful ablation of the
    full method.
    """

    certificate_outcome_atoms: list[OutcomeAtom] = field(default_factory=list)

    def score_atoms(self, atoms: list[Atom]) -> list[float]:
        cert: Counter = Counter()
        for a in self.certificate_outcome_atoms:
            cert.update(tokenize(a.content))
        return [cosine(Counter(tokenize(a.content)), cert) for a in atoms]

    def select_atoms(self, atoms, budget_tokens=None, threshold=None):
        return _select_by_scores(atoms, self.score_atoms(atoms), budget_tokens, threshold)
