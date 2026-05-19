"""Load trajectories from JSON.

Expected schema (all `metadata` fields optional)::

    {
      "id": "...", "task_id": "...", "domain": "...",
      "steps": [
        {"id": "...", "index": 0, "step_type": "user_message",
         "content": "...", "input_refs": [], "output_refs": []}
      ],
      "final_outcome": {
        "id": "...", "task_id": "...", "domain": "...",
        "content": "...", "artifacts": []
      }
    }
"""

from __future__ import annotations

import json
from typing import Any

from core.outcome import Outcome
from core.trajectory import Trajectory, TrajectoryStep


def _step_from_dict(d: dict[str, Any], index: int) -> TrajectoryStep:
    return TrajectoryStep(
        id=d.get("id", f"step-{index}"),
        index=d.get("index", index),
        step_type=d["step_type"],
        content=d.get("content", ""),
        input_refs=list(d.get("input_refs", [])),
        output_refs=list(d.get("output_refs", [])),
        metadata=dict(d.get("metadata", {})),
    )


def _outcome_from_dict(d: dict[str, Any], task_id: str, domain: str) -> Outcome:
    return Outcome(
        id=d.get("id", f"{task_id}-outcome"),
        task_id=d.get("task_id", task_id),
        domain=d.get("domain", domain),
        content=d.get("content", ""),
        artifacts=list(d.get("artifacts", [])),
        metadata=dict(d.get("metadata", {})),
    )


def trajectory_from_dict(data: dict[str, Any]) -> Trajectory:
    """Parse an already-deserialized dict into a Trajectory."""
    task_id = data["task_id"]
    domain = data.get("domain", "unknown")
    steps = [_step_from_dict(s, i) for i, s in enumerate(data.get("steps", []))]
    outcome = _outcome_from_dict(data["final_outcome"], task_id, domain)
    return Trajectory(
        id=data.get("id", f"{task_id}-traj"),
        task_id=task_id,
        domain=domain,
        steps=steps,
        final_outcome=outcome,
        metadata=dict(data.get("metadata", {})),
    )


class JSONTrajectoryLoader:
    """A TrajectoryLoader backed by a JSON file on disk."""

    def load(self, path: str) -> Trajectory:
        with open(path, encoding="utf-8") as fh:
            return trajectory_from_dict(json.load(fh))

    def loads(self, text: str) -> Trajectory:
        return trajectory_from_dict(json.loads(text))
