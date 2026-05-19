"""The general Atomizer interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.atoms import Atom, OutcomeAtom
from core.outcome import Outcome
from core.trajectory import Trajectory


@runtime_checkable
class Atomizer(Protocol):
    """Splits a trajectory and an outcome into atoms.

    Implementations may be generic or domain-specific; everything downstream
    consumes only the resulting `Atom` / `OutcomeAtom` lists.
    """

    def atomize_trajectory(self, trajectory: Trajectory) -> list[Atom]: ...

    def atomize_outcome(self, outcome: Outcome) -> list[OutcomeAtom]: ...
