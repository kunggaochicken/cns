"""The general TrajectoryLoader interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.trajectory import Trajectory


@runtime_checkable
class TrajectoryLoader(Protocol):
    """Loads a trajectory from some serialized form into the core data model."""

    def load(self, path: str) -> Trajectory: ...
