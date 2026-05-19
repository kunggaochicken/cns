"""Atoms: the smallest units a trajectory or outcome is decomposed into."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Atom type constants. Kept as plain strings (not an enum) so domain-specific
# atomizers can introduce their own types without touching the core.
ATOM_TYPES = [
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
    "outcome_atom",
]


def count_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate (whitespace words).

    A real system would plug in a tokenizer; the framework only needs a
    monotone, additive cost proxy.
    """
    return max(1, len((text or "").split()))


@dataclass
class Atom:
    """An atomic unit of trajectory content."""

    id: str
    trajectory_id: str
    step_id: str | None
    atom_type: str
    content: str
    token_count: int
    timestamp: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        id: str,
        trajectory_id: str,
        step_id: str | None,
        atom_type: str,
        content: str,
        **kwargs: Any,
    ) -> Atom:
        """Construct an atom, computing `token_count` from `content`."""
        return cls(
            id=id,
            trajectory_id=trajectory_id,
            step_id=step_id,
            atom_type=atom_type,
            content=content,
            token_count=count_tokens(content),
            timestamp=kwargs.pop("timestamp", None),
            metadata=kwargs.pop("metadata", {}) or {},
        )


@dataclass
class OutcomeAtom(Atom):
    """An atomic unit of the *final outcome*.

    Carries oracle-derived annotations: how relevant the oracle judged it,
    whether it is necessary for success, and which sufficient group it belongs
    to (atoms that are interchangeable for satisfying the task).
    """

    oracle_relevance_score: float | None = None
    necessary: bool | None = None
    sufficient_group_id: str | None = None

    @classmethod
    def create(
        cls,
        id: str,
        trajectory_id: str,
        step_id: str | None,
        atom_type: str,
        content: str,
        **kwargs: Any,
    ) -> OutcomeAtom:
        return cls(
            id=id,
            trajectory_id=trajectory_id,
            step_id=step_id,
            atom_type=atom_type or "outcome_atom",
            content=content,
            token_count=count_tokens(content),
            timestamp=kwargs.pop("timestamp", None),
            metadata=kwargs.pop("metadata", {}) or {},
            oracle_relevance_score=kwargs.pop("oracle_relevance_score", None),
            necessary=kwargs.pop("necessary", None),
            sufficient_group_id=kwargs.pop("sufficient_group_id", None),
        )
