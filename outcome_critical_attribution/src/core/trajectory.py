"""Agent trajectories: the ordered record of what an agent did."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.outcome import Outcome

# Step type constants. Plain strings for the same extensibility reason as
# ATOM_TYPES -- a new domain can record step types the core never enumerated.
STEP_TYPES = [
    "user_message",
    "system_message",
    "assistant_message",
    "reasoning_summary",
    "plan",
    "action",
    "tool_call",
    "tool_result",
    "observation",
    "environment_state",
    "memory_retrieval",
    "artifact_creation",
    "artifact_edit",
    "final_response",
    "final_state",
]


@dataclass
class TrajectoryStep:
    """One step in a trajectory.

    `input_refs` / `output_refs` are ids of other steps (or external objects)
    this step consumed / produced. They give the attribution layer a cheap,
    domain-supplied prior on information flow.
    """

    id: str
    index: int
    step_type: str
    content: str
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trajectory:
    """A full agent trajectory plus the outcome it terminated in."""

    id: str
    task_id: str
    domain: str
    steps: list[TrajectoryStep]
    final_outcome: Outcome
    metadata: dict[str, Any] = field(default_factory=dict)

    def step_by_id(self, step_id: str) -> TrajectoryStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def total_tokens(self) -> int:
        return sum(len(s.content.split()) for s in self.steps)
