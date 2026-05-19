"""Greedy outcome-atom minimization.

Repeatedly tries to drop each remaining atom; keeps the drop whenever the
oracle still reports success. Converges to a *locally* minimal certificate
(no single atom can be removed) in O(n^2) oracle calls.
"""

from __future__ import annotations

from core.atoms import OutcomeAtom
from core.oracle import OutcomeOracle
from core.task import Task

from ablation.base import SuccessCertificate, certificate_cost


def greedy_minimize_outcome_atoms(
    task: Task,
    outcome_atoms: list[OutcomeAtom],
    oracle: OutcomeOracle,
) -> SuccessCertificate:
    """Return the minimal success certificate found by greedy deletion.

    If the oracle does not accept the full set, the certificate is the full
    set with `oracle_score` from that failing evaluation -- callers should
    check `metadata["initial_success"]`.
    """
    base = oracle.evaluate(task, outcome_atoms)
    if not base.success:
        return SuccessCertificate(
            task_id=task.id,
            outcome_atom_ids=[a.id for a in outcome_atoms],
            oracle_score=base.score,
            cost=certificate_cost(outcome_atoms),
            metadata={"initial_success": False, "n_oracle_calls": 1},
        )

    current = list(outcome_atoms)
    calls = 1
    # Drop the most expensive atoms first -- a cheap bias toward lower cost.
    changed = True
    while changed:
        changed = False
        for atom in sorted(current, key=lambda a: -a.token_count):
            if atom not in current:
                continue
            candidate = [a for a in current if a.id != atom.id]
            result = oracle.evaluate(task, candidate)
            calls += 1
            if result.success:
                current = candidate
                changed = True

    final = oracle.evaluate(task, current)
    calls += 1
    return SuccessCertificate(
        task_id=task.id,
        outcome_atom_ids=[a.id for a in current],
        oracle_score=final.score,
        cost=certificate_cost(current),
        metadata={
            "initial_success": True,
            "n_oracle_calls": calls,
            "method": "greedy",
        },
    )


class GreedyAblator:
    """OutcomeAblator wrapper around `greedy_minimize_outcome_atoms`."""

    def minimize(
        self,
        task: Task,
        outcome_atoms: list[OutcomeAtom],
        oracle: OutcomeOracle,
    ) -> SuccessCertificate:
        return greedy_minimize_outcome_atoms(task, outcome_atoms, oracle)
