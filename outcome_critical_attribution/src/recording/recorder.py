"""Live recording of agent trajectories.

A TrajectoryRecorder is the write-side counterpart of a loader: an agent calls
into it as it runs, and at the end gets back a `Trajectory`.
"""

from __future__ import annotations

from typing import Any

from core.outcome import Outcome
from core.trajectory import Trajectory, TrajectoryStep


class TrajectoryRecorder:
    """Accumulates steps for one task and finalizes them into a Trajectory."""

    def __init__(self) -> None:
        self._task_id: str | None = None
        self._domain: str | None = None
        self._prompt: str | None = None
        self._steps: list[TrajectoryStep] = []

    def start_task(self, task_id: str, domain: str, prompt: str) -> None:
        self._task_id = task_id
        self._domain = domain
        self._prompt = prompt
        self._steps = [
            TrajectoryStep(
                id=f"{task_id}-step-0",
                index=0,
                step_type="user_message",
                content=prompt,
            )
        ]

    def record_step(self, step: TrajectoryStep) -> None:
        if self._task_id is None:
            raise RuntimeError("call start_task before record_step")
        self._steps.append(step)

    def record(
        self,
        step_type: str,
        content: str,
        input_refs: list[str] | None = None,
        output_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TrajectoryStep:
        """Convenience: build and append a step with an auto index/id."""
        if self._task_id is None:
            raise RuntimeError("call start_task before record")
        index = len(self._steps)
        step = TrajectoryStep(
            id=f"{self._task_id}-step-{index}",
            index=index,
            step_type=step_type,
            content=content,
            input_refs=input_refs or [],
            output_refs=output_refs or [],
            metadata=metadata or {},
        )
        self._steps.append(step)
        return step

    def finish_task(self, final_outcome: Outcome) -> Trajectory:
        if self._task_id is None or self._domain is None:
            raise RuntimeError("call start_task before finish_task")
        return Trajectory(
            id=f"{self._task_id}-traj",
            task_id=self._task_id,
            domain=self._domain,
            steps=list(self._steps),
            final_outcome=final_outcome,
        )
