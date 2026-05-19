"""Beam-search outcome-atom minimization.

Greedy deletion can get stuck in a local minimum. Beam search keeps the
`beam_width` cheapest still-successful subsets at each depth and expands all of
them by one more deletion, exploring more of the lattice for a small constant
factor more oracle calls.
"""

from __future__ import annotations

from core.atoms import OutcomeAtom
from core.oracle import OutcomeOracle
from core.task import Task

from ablation.base import SuccessCertificate, certificate_cost


def beam_minimize_outcome_atoms(
    task: Task,
    outcome_atoms: list[OutcomeAtom],
    oracle: OutcomeOracle,
    beam_width: int = 4,
) -> SuccessCertificate:
    """Return the cheapest success certificate found by beam search."""
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

    by_id = {a.id: a for a in outcome_atoms}
    full = frozenset(by_id)
    # Beam of successful candidate id-sets, plus the best seen so far.
    beam: list[frozenset[str]] = [full]
    best: frozenset[str] = full
    seen: set[frozenset[str]] = {full}

    def cost(ids: frozenset[str]) -> int:
        return sum(by_id[i].token_count for i in ids)

    while beam:
        successors: list[frozenset[str]] = []
        for state in beam:
            for atom_id in state:
                child = state - {atom_id}
                if not child or child in seen:
                    continue
                seen.add(child)
                result = oracle.evaluate(task, [by_id[i] for i in child])
                calls += 1
                if result.success:
                    successors.append(child)
                    if cost(child) < cost(best):
                        best = child
        successors.sort(key=cost)
        beam = successors[:beam_width]

    final_atoms = [by_id[i] for i in best]
    final = oracle.evaluate(task, final_atoms)
    calls += 1
    return SuccessCertificate(
        task_id=task.id,
        outcome_atom_ids=[a.id for a in final_atoms],
        oracle_score=final.score,
        cost=certificate_cost(final_atoms),
        metadata={
            "initial_success": True,
            "n_oracle_calls": calls,
            "method": "beam",
            "beam_width": beam_width,
        },
    )


class BeamAblator:
    """OutcomeAblator wrapper around `beam_minimize_outcome_atoms`."""

    def __init__(self, beam_width: int = 4) -> None:
        self.beam_width = beam_width

    def minimize(
        self,
        task: Task,
        outcome_atoms: list[OutcomeAtom],
        oracle: OutcomeOracle,
    ) -> SuccessCertificate:
        return beam_minimize_outcome_atoms(task, outcome_atoms, oracle, self.beam_width)
