"""The general AttributionModel interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.atoms import Atom, OutcomeAtom
from core.graph import AttributionGraph


@runtime_checkable
class AttributionModel(Protocol):
    """Produces an attribution graph from trajectory atoms to outcome atoms.

    The output is a *graph*, not scalar importances: edges carry direction,
    weight, and (ideally) evidence, so the support extractor can reason about
    information flow rather than just rank atoms.
    """

    def attribute(
        self,
        trajectory_atoms: list[Atom],
        outcome_atoms: list[OutcomeAtom],
    ) -> AttributionGraph: ...
