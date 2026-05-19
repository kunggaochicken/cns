"""The outcome oracle: a domain-specific judge behind a general interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.atoms import OutcomeAtom
from core.task import Task


@dataclass
class OracleResult:
    """Verdict of an oracle on a candidate set of outcome atoms."""

    success: bool
    score: float
    explanation: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class OutcomeOracle(ABC):
    """Decides whether a subset of outcome atoms still satisfies a task.

    Concrete oracles are domain-specific (run tests, check a DOM, fact-check an
    answer). The core framework only ever calls `evaluate`.
    """

    @abstractmethod
    def evaluate(
        self,
        task: Task,
        outcome_atoms: list[OutcomeAtom],
        context: dict[str, Any] | None = None,
    ) -> OracleResult: ...


class MockOracle(OutcomeOracle):
    """A deterministic oracle for tests, toy examples, and CI.

    Success requires that every `required_keyword` appears somewhere in the
    candidate atoms, every id in `required_atom_ids` is present, and at least
    `min_atoms` atoms remain. This makes the minimal success certificate
    well-defined and predictable.
    """

    def __init__(
        self,
        required_keywords: list[str] | None = None,
        required_atom_ids: list[str] | None = None,
        min_atoms: int = 0,
    ) -> None:
        self.required_keywords = [k.lower() for k in (required_keywords or [])]
        self.required_atom_ids = set(required_atom_ids or [])
        self.min_atoms = min_atoms

    def evaluate(
        self,
        task: Task,
        outcome_atoms: list[OutcomeAtom],
        context: dict[str, Any] | None = None,
    ) -> OracleResult:
        ids = {a.id for a in outcome_atoms}
        blob = " \n ".join(a.content.lower() for a in outcome_atoms)

        missing_ids = sorted(self.required_atom_ids - ids)
        missing_kw = [k for k in self.required_keywords if k not in blob]
        enough = len(outcome_atoms) >= self.min_atoms

        total_reqs = len(self.required_atom_ids) + len(self.required_keywords)
        missing = len(missing_ids) + len(missing_kw)
        satisfied = total_reqs - missing
        score = 1.0 if total_reqs == 0 else satisfied / total_reqs

        success = not missing_ids and not missing_kw and enough
        explanation = (
            "all requirements satisfied"
            if success
            else f"missing keywords={missing_kw} missing_ids={missing_ids} enough_atoms={enough}"
        )
        return OracleResult(
            success=success,
            score=score if success else min(score, 0.99),
            explanation=explanation,
            diagnostics={
                "missing_keywords": missing_kw,
                "missing_atom_ids": missing_ids,
                "n_atoms": len(outcome_atoms),
            },
        )
