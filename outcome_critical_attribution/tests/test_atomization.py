from atomization.generic import GenericAtomizer
from atomization.messages import split_units
from core.outcome import Outcome
from core.trajectory import Trajectory, TrajectoryStep


def test_split_units_paragraphs_and_sentences():
    text = "First paragraph. Second sentence here.\n\nNew para in here."
    units = split_units(text)
    assert "First paragraph." in units
    assert "Second sentence here." in units
    assert "New para in here." in units


def test_split_units_bullets():
    text = "- one\n- two\n- three"
    assert split_units(text) == ["one", "two", "three"]


def _trajectory():
    steps = [
        TrajectoryStep(id="s0", index=0, step_type="user_message", content="please do X."),
        TrajectoryStep(
            id="s1",
            index=1,
            step_type="tool_result",
            content="result line one.\nresult line two: detail.",
        ),
    ]
    return Trajectory(
        id="traj",
        task_id="t1",
        domain="d",
        steps=steps,
        final_outcome=Outcome(
            id="o",
            task_id="t1",
            domain="d",
            content="answer A. answer B.",
        ),
    )


def test_generic_atomizer_splits_trajectory_and_outcome():
    a = GenericAtomizer()
    traj = _trajectory()
    atoms = a.atomize_trajectory(traj)
    outcome_atoms = a.atomize_outcome(traj.final_outcome)
    assert len(atoms) >= len(traj.steps)
    assert len(outcome_atoms) >= 2
    assert all(o.atom_type == "outcome_atom" for o in outcome_atoms)
    # Atoms reference their originating step.
    assert {a.step_id for a in atoms} == {"s0", "s1"}
