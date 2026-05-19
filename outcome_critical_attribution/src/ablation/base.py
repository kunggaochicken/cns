"""Ablation interface and the SuccessCertificate data model.

A *success certificate* is the minimal (lowest-cost) subset of outcome atoms
that the oracle still accepts as a success. It is the heart of the framework:
it pins down *what actually mattered* about the outcome, as opposed to what the
agent happened to also produce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from core.atoms import OutcomeAtom
from core.oracle import OutcomeOracle
from core.task import Task


@dataclass
class SuccessCertificate:
    """The minimal set of outcome atoms that still yields success."""

    task_id: str
    outcome_atom_ids: list[str]
    oracle_score: float
    cost: int
    metadata: dict[str, Any] = field(default_factory=dict)


def certificate_cost(atoms: list[OutcomeAtom]) -> int:
    return sum(a.token_count for a in atoms)


@runtime_checkable
class OutcomeAblator(Protocol):
    """Reduces a set of outcome atoms to a minimal success certificate."""

    def minimize(
        self,
        task: Task,
        outcome_atoms: list[OutcomeAtom],
        oracle: OutcomeOracle,
    ) -> SuccessCertificate: ...
