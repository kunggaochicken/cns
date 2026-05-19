"""A domain-agnostic atomizer.

GenericAtomizer splits every trajectory step and the final outcome into
claim-sized atoms using simple structural heuristics (paragraphs, bullets,
sentences, artifact sections). Domain-specific atomizers can subclass it and
override `_units_for_step` / `_units_for_outcome`.
"""

from __future__ import annotations

from core.atoms import Atom, OutcomeAtom
from core.outcome import Outcome
from core.trajectory import Trajectory, TrajectoryStep

from atomization.artifacts import split_artifact_sections
from atomization.messages import split_units

# How each trajectory step type maps onto an atom type.
_STEP_TO_ATOM = {
    "user_message": "instruction",
    "system_message": "constraint",
    "assistant_message": "decision",
    "reasoning_summary": "decision",
    "plan": "plan",
    "action": "decision",
    "tool_call": "tool_input",
    "tool_result": "tool_output",
    "observation": "observation",
    "environment_state": "environment_fact",
    "memory_retrieval": "memory",
    "artifact_creation": "artifact_atom",
    "artifact_edit": "artifact_atom",
    "final_response": "final_response_atom",
    "final_state": "environment_fact",
}

_ARTIFACT_STEPS = {"artifact_creation", "artifact_edit"}


class GenericAtomizer:
    """Generic, structure-based atomizer (implements the Atomizer protocol)."""

    def __init__(self, min_atom_chars: int = 1) -> None:
        self.min_atom_chars = min_atom_chars

    def _units_for_step(self, step: TrajectoryStep) -> list[str]:
        if step.step_type in _ARTIFACT_STEPS:
            return split_artifact_sections(step.content)
        return split_units(step.content)

    def _units_for_outcome(self, outcome: Outcome) -> list[str]:
        return split_units(outcome.content)

    def atomize_trajectory(self, trajectory: Trajectory) -> list[Atom]:
        atoms: list[Atom] = []
        for step in trajectory.steps:
            atom_type = _STEP_TO_ATOM.get(step.step_type, "observation")
            for j, unit in enumerate(self._units_for_step(step)):
                if len(unit) < self.min_atom_chars:
                    continue
                atoms.append(
                    Atom.create(
                        id=f"{step.id}-atom-{j}",
                        trajectory_id=trajectory.id,
                        step_id=step.id,
                        atom_type=atom_type,
                        content=unit,
                        timestamp=str(step.index),
                        metadata={
                            "step_type": step.step_type,
                            "step_index": step.index,
                        },
                    )
                )
        return atoms

    def atomize_outcome(self, outcome: Outcome) -> list[OutcomeAtom]:
        atoms: list[OutcomeAtom] = []
        for j, unit in enumerate(self._units_for_outcome(outcome)):
            if len(unit) < self.min_atom_chars:
                continue
            atoms.append(
                OutcomeAtom.create(
                    id=f"{outcome.id}-oatom-{j}",
                    trajectory_id=outcome.task_id,
                    step_id=None,
                    atom_type="outcome_atom",
                    content=unit,
                    metadata={"outcome_id": outcome.id},
                )
            )
        return atoms
