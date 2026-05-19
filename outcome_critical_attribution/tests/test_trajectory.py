from core.outcome import Outcome
from core.trajectory import Trajectory, TrajectoryStep
from recording.json_loader import trajectory_from_dict
from recording.recorder import TrajectoryRecorder


def _outcome():
    return Outcome(id="o", task_id="t1", domain="d", content="done")


def test_trajectory_step_by_id_and_tokens():
    steps = [
        TrajectoryStep(id="s0", index=0, step_type="user_message", content="hi there"),
        TrajectoryStep(id="s1", index=1, step_type="assistant_message", content="hello you world"),
    ]
    traj = Trajectory(id="x", task_id="t1", domain="d", steps=steps, final_outcome=_outcome())
    assert traj.step_by_id("s1").content == "hello you world"
    assert traj.step_by_id("missing") is None
    assert traj.total_tokens() == 2 + 3


def test_json_loader_roundtrip():
    data = {
        "id": "traj",
        "task_id": "t1",
        "domain": "research",
        "steps": [
            {"id": "s0", "index": 0, "step_type": "user_message", "content": "q"},
            {"id": "s1", "index": 1, "step_type": "assistant_message", "content": "a"},
        ],
        "final_outcome": {"id": "o", "task_id": "t1", "domain": "research", "content": "done"},
    }
    traj = trajectory_from_dict(data)
    assert traj.task_id == "t1"
    assert len(traj.steps) == 2
    assert traj.final_outcome.content == "done"


def test_trajectory_recorder_collects_steps():
    rec = TrajectoryRecorder()
    rec.start_task("t1", "research", "what year?")
    rec.record("plan", "search the web")
    rec.record("tool_result", "the year is 2023")
    traj = rec.finish_task(_outcome())
    assert traj.task_id == "t1"
    # user_message + plan + tool_result == 3 steps.
    assert [s.step_type for s in traj.steps] == [
        "user_message",
        "plan",
        "tool_result",
    ]
