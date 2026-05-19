from core.atoms import Atom
from evaluation.metrics import (
    attribution_f1,
    attribution_precision,
    attribution_recall,
    compression_ratio,
    cost_success_frontier,
    success_retention,
    token_savings,
)


def _atom(aid, tokens):
    a = Atom.create(aid, "t", "s", "observation", "x " * tokens)
    return a


def test_success_retention_and_oracle():
    assert success_retention(1.0, 0.8) == 0.8
    assert success_retention(0.0, 0.0) == 0.0


def test_compression_and_savings():
    all_atoms = [_atom(f"a{i}", i + 1) for i in range(4)]
    selected = [all_atoms[0], all_atoms[2]]
    assert compression_ratio(selected, all_atoms) == 0.5
    total = sum(a.token_count for a in all_atoms)
    kept = sum(a.token_count for a in selected)
    assert abs(token_savings(selected, all_atoms) - (1 - kept / total)) < 1e-9


def test_attribution_prf():
    predicted = {"a", "b", "c"}
    gold = {"b", "c", "d"}
    assert abs(attribution_precision(predicted, gold) - 2 / 3) < 1e-9
    assert abs(attribution_recall(predicted, gold) - 2 / 3) < 1e-9
    assert abs(attribution_f1(predicted, gold) - 2 / 3) < 1e-9


def test_cost_success_frontier_is_pareto():
    points = [(0.2, 0.5), (0.4, 0.7), (0.4, 0.6), (0.6, 0.8), (0.8, 0.4)]
    front = cost_success_frontier(points)
    # All dominated points removed; remaining strictly improving in success
    # as savings increases (until the trailing drop).
    assert (0.4, 0.6) not in front
    assert (0.6, 0.8) in front
