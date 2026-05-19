"""Evaluation metrics for context compression and attribution quality."""

from __future__ import annotations

from collections.abc import Iterable

from core.atoms import Atom


def success_retention(original_success_rate: float, compressed_success_rate: float) -> float:
    """Fraction of the original success rate preserved after compression.

    1.0 means compression cost nothing; <1.0 means some tasks now fail.
    """
    if original_success_rate <= 0:
        return 0.0
    return compressed_success_rate / original_success_rate


def oracle_score_retention(original_score: float, compressed_score: float) -> float:
    """Ratio of oracle scores, compressed vs original."""
    if original_score <= 0:
        return 0.0
    return compressed_score / original_score


def compression_ratio(selected_atoms: Iterable[Atom], all_atoms: Iterable[Atom]) -> float:
    """Fraction of atoms retained (by count). Lower = more compression."""
    total = len(list(all_atoms))
    if total == 0:
        return 0.0
    return len(list(selected_atoms)) / total


def token_savings(selected_atoms: Iterable[Atom], all_atoms: Iterable[Atom]) -> float:
    """Fraction of tokens removed. Higher = more savings."""
    total = sum(a.token_count for a in all_atoms)
    if total == 0:
        return 0.0
    kept = sum(a.token_count for a in selected_atoms)
    return 1.0 - kept / total


def _prf(predicted: set[str], gold: set[str]) -> tuple[float, float, float]:
    if not predicted and not gold:
        return 1.0, 1.0, 1.0
    tp = len(predicted & gold)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def attribution_precision(predicted_support: Iterable[str], gold_support: Iterable[str]) -> float:
    """Of the atoms the policy kept, how many are in the gold support set."""
    return _prf(set(predicted_support), set(gold_support))[0]


def attribution_recall(predicted_support: Iterable[str], gold_support: Iterable[str]) -> float:
    """Of the gold support atoms, how many did the policy keep."""
    return _prf(set(predicted_support), set(gold_support))[1]


def attribution_f1(predicted_support: Iterable[str], gold_support: Iterable[str]) -> float:
    return _prf(set(predicted_support), set(gold_support))[2]


def cost_success_frontier(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pareto frontier over (token_savings, success_retention) points.

    Returns the non-dominated points sorted by token savings -- the curve the
    main experiment plots one policy against another on.
    """
    pts = sorted(set(points), key=lambda p: (p[0], p[1]))
    frontier: list[tuple[float, float]] = []
    best_success = -1.0
    for savings, success in reversed(pts):
        if success > best_success:
            frontier.append((savings, success))
            best_success = success
    return list(reversed(frontier))
