"""End-to-end benchmark harness.

Given a set of (trajectory atoms, outcome atoms, oracle, certificate, support
graph) bundles, evaluates every policy in a name->policy dict over a sweep of
token budgets and returns a frontier per policy plus attribution P/R/F1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ablation.base import SuccessCertificate
from core.atoms import Atom, OutcomeAtom
from core.oracle import OutcomeOracle
from core.task import Task
from policy.model import ContextPolicy

from evaluation.metrics import (
    attribution_f1,
    attribution_precision,
    attribution_recall,
    cost_success_frontier,
    success_retention,
    token_savings,
)


@dataclass
class BenchmarkBundle:
    """One task's worth of evaluation inputs."""

    task: Task
    trajectory_atoms: list[Atom]
    outcome_atoms: list[OutcomeAtom]
    oracle: OutcomeOracle
    certificate: SuccessCertificate
    gold_support_atom_ids: list[str]


@dataclass
class PolicyEvaluation:
    """Per-policy aggregated results across the bundle set."""

    name: str
    frontier: list[tuple[float, float]]
    attribution_precision: float
    attribution_recall: float
    attribution_f1: float
    per_budget: dict[float, dict[str, float]] = field(default_factory=dict)


def _success_at(bundle: BenchmarkBundle, kept: list[Atom]) -> float:
    """Stand-in success oracle on a compressed trajectory.

    The oracle is defined on outcome atoms, not trajectory atoms, so we
    approximate "would this still succeed?" by checking that every certificate
    outcome atom has at least one supporting (kept) trajectory atom that
    overlaps it lexically. This is the same proxy the AblationOnly baseline
    uses and is cheap, deterministic, and monotone in the right direction.
    """
    from collections import Counter

    from attribution.graph_builder import cosine, tokenize

    if not bundle.certificate.outcome_atom_ids:
        return 1.0

    cert_atoms = [
        a for a in bundle.outcome_atoms if a.id in set(bundle.certificate.outcome_atom_ids)
    ]
    kept_vecs = [Counter(tokenize(a.content)) for a in kept]
    covered = 0
    for atom in cert_atoms:
        ovec = Counter(tokenize(atom.content))
        if any(cosine(kv, ovec) >= 0.15 for kv in kept_vecs):
            covered += 1
    return covered / max(1, len(cert_atoms))


def evaluate_policy(
    name: str,
    policy: ContextPolicy,
    bundles: list[BenchmarkBundle],
    budgets: list[float],
) -> PolicyEvaluation:
    """Sweep `policy` across token budgets (as fractions of full context)."""
    points: list[tuple[float, float]] = []
    per_budget: dict[float, dict[str, float]] = {}

    full_success = sum(_success_at(b, b.trajectory_atoms) for b in bundles) / max(1, len(bundles))

    # Attribution P/R/F1: use the budget=1.0 / threshold=median selection.
    pred_ids: set[str] = set()
    gold_ids: set[str] = set()
    for b in bundles:
        kept = policy.select_atoms(b.trajectory_atoms)
        pred_ids.update(a.id for a in kept)
        gold_ids.update(b.gold_support_atom_ids)
    precision = attribution_precision(pred_ids, gold_ids)
    recall = attribution_recall(pred_ids, gold_ids)
    f1 = attribution_f1(pred_ids, gold_ids)

    for budget_frac in budgets:
        successes = []
        savings_per_bundle = []
        for b in bundles:
            total_tokens = sum(a.token_count for a in b.trajectory_atoms)
            budget = max(1, int(round(total_tokens * budget_frac)))
            kept = policy.select_atoms(b.trajectory_atoms, budget_tokens=budget)
            successes.append(_success_at(b, kept))
            savings_per_bundle.append(token_savings(kept, b.trajectory_atoms))
        avg_success = sum(successes) / max(1, len(successes))
        avg_savings = sum(savings_per_bundle) / max(1, len(savings_per_bundle))
        retention = success_retention(full_success, avg_success)
        points.append((avg_savings, retention))
        per_budget[budget_frac] = {
            "avg_success": avg_success,
            "avg_token_savings": avg_savings,
            "success_retention": retention,
        }

    return PolicyEvaluation(
        name=name,
        frontier=cost_success_frontier(points),
        attribution_precision=precision,
        attribution_recall=recall,
        attribution_f1=f1,
        per_budget=per_budget,
    )


def run_benchmark(
    policies: dict[str, ContextPolicy],
    bundles: list[BenchmarkBundle],
    budgets: list[float] | None = None,
) -> dict[str, PolicyEvaluation]:
    """Evaluate every policy across a budget sweep."""
    budgets = budgets or [0.1, 0.25, 0.5, 0.75, 1.0]
    return {
        name: evaluate_policy(name, policy, bundles, budgets) for name, policy in policies.items()
    }


def format_benchmark(results: dict[str, PolicyEvaluation]) -> str:
    """Pretty-print a benchmark result dict for terminal inspection."""
    lines = ["policy             |  P    R    F1   | frontier (savings, success)"]
    lines.append("-" * 78)
    for name, res in results.items():
        front = ", ".join(f"({s:.2f},{r:.2f})" for s, r in res.frontier)
        lines.append(
            f"{name:<18s} | {res.attribution_precision:.2f} "
            f"{res.attribution_recall:.2f} {res.attribution_f1:.2f} | {front}"
        )
    return "\n".join(lines)
