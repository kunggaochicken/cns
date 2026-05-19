"""Delta-debugging (ddmin) outcome-atom minimization.

Adapts Zeller's ddmin: instead of isolating a failure, it isolates the subset
of outcome atoms that *preserves success*. It tries to remove large chunks
first, so it is much faster than greedy when many atoms are irrelevant.
"""

from __future__ import annotations

from core.atoms import OutcomeAtom
from core.oracle import OutcomeOracle
from core.task import Task

from ablation.base import SuccessCertificate, certificate_cost


def ddmin_minimize_outcome_atoms(
    task: Task,
    outcome_atoms: list[OutcomeAtom],
    oracle: OutcomeOracle,
) -> SuccessCertificate:
    """Return a 1-minimal success certificate via ddmin-style search."""
    base = oracle.evaluate(task, outcome_atoms)
    calls = 1
    if not base.success:
        return SuccessCertificate(
            task_id=task.id,
            outcome_atom_ids=[a.id for a in outcome_atoms],
            oracle_score=base.score,
            cost=certificate_cost(outcome_atoms),
            metadata={"initial_success": False, "n_oracle_calls": calls},
        )

    current = list(outcome_atoms)
    n = 2
    while len(current) >= 2:
        chunk = max(1, len(current) // n)
        subsets = [current[i : i + chunk] for i in range(0, len(current), chunk)]
        reduced = False

        # Try keeping just one subset (aggressive removal of the complement).
        for subset in subsets:
            res = oracle.evaluate(task, subset)
            calls += 1
            if res.success:
                current = subset
                n = 2
                reduced = True
                break
        if reduced:
            continue

        # Try removing one subset at a time (the complement).
        for subset in subsets:
            keep_ids = {a.id for a in subset}
            complement = [a for a in current if a.id not in keep_ids]
            if not complement:
                continue
            res = oracle.evaluate(task, complement)
            calls += 1
            if res.success:
                current = complement
                n = max(n - 1, 2)
                reduced = True
                break
        if reduced:
            continue

        if n >= len(current):
            break
        n = min(len(current), n * 2)

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
            "method": "delta_debugging",
        },
    )


class DeltaDebuggingAblator:
    """OutcomeAblator wrapper around `ddmin_minimize_outcome_atoms`."""

    def minimize(
        self,
        task: Task,
        outcome_atoms: list[OutcomeAtom],
        oracle: OutcomeOracle,
    ) -> SuccessCertificate:
        return ddmin_minimize_outcome_atoms(task, outcome_atoms, oracle)
