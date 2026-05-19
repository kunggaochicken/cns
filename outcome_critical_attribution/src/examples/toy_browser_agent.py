"""End-to-end pipeline on a tiny browser-agent trajectory.

Run:  python src/examples/toy_browser_agent.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ablation.greedy import GreedyAblator
from atomization.generic import GenericAtomizer
from attribution.graph_builder import HeuristicAttributor
from attribution.support_extractor import extract_topk_support
from core.oracle import MockOracle
from core.outcome import Outcome
from core.task import Task
from core.trajectory import Trajectory, TrajectoryStep
from evaluation.baselines import EmbeddingSimilarityPolicy, RecencyPolicy
from evaluation.benchmark import BenchmarkBundle, format_benchmark, run_benchmark
from policy.dataset import build_training_example
from policy.train import train_policy


def main() -> None:
    steps = [
        TrajectoryStep(
            id="s0",
            index=0,
            step_type="user_message",
            content="Sign me up for the weekly newsletter on example.com with my email.",
        ),
        TrajectoryStep(
            id="s1", index=1, step_type="action", content="Navigate to https://example.com"
        ),
        TrajectoryStep(
            id="s2",
            index=2,
            step_type="observation",
            content="Page loaded. Hero banner: 'Welcome to Example'. Newsletter link in footer.",
        ),
        TrajectoryStep(
            id="s3", index=3, step_type="action", content="Click footer link 'Newsletter'"
        ),
        TrajectoryStep(
            id="s4",
            index=4,
            step_type="observation",
            content=(
                "Newsletter page shown. Form has email field and frequency dropdown. "
                "Promotional carousel rotates unrelated product images."
            ),
        ),
        TrajectoryStep(
            id="s5",
            index=5,
            step_type="action",
            content="Type 'user@example.com' into the email input.",
        ),
        TrajectoryStep(
            id="s6",
            index=6,
            step_type="action",
            content="Select frequency='weekly' from the dropdown.",
        ),
        TrajectoryStep(id="s7", index=7, step_type="action", content="Click button 'Subscribe'."),
        TrajectoryStep(
            id="s8",
            index=8,
            step_type="observation",
            content="Confirmation banner: 'You are subscribed to the weekly newsletter.'",
        ),
        TrajectoryStep(
            id="s9",
            index=9,
            step_type="final_state",
            content=(
                "Subscribed user@example.com to example.com newsletter at weekly frequency. "
                "Promotional carousel content is irrelevant to the task."
            ),
        ),
    ]
    outcome = Outcome(
        id="o-browser",
        task_id="t-browser",
        domain="browser",
        content=(
            "user@example.com subscribed to example.com newsletter with frequency=weekly. "
            "Confirmation banner observed. Promotional carousel content noted."
        ),
    )
    trajectory = Trajectory(
        id="traj-browser",
        task_id="t-browser",
        domain="browser",
        steps=steps,
        final_outcome=outcome,
    )
    task = Task(id=trajectory.task_id, domain="browser", prompt=steps[0].content)

    atomizer = GenericAtomizer()
    trajectory_atoms = atomizer.atomize_trajectory(trajectory)
    outcome_atoms = atomizer.atomize_outcome(outcome)

    oracle = MockOracle(required_keywords=["user@example.com", "weekly", "subscribed"])
    certificate = GreedyAblator().minimize(task, outcome_atoms, oracle)

    graph = HeuristicAttributor().attribute(trajectory_atoms, outcome_atoms)
    support = extract_topk_support(graph, certificate, k_per_outcome=3)
    example = build_training_example(
        task_id=task.id,
        domain="browser",
        trajectory_atoms=trajectory_atoms,
        outcome_atoms=outcome_atoms,
        certificate=certificate,
        attribution_graph=graph,
        support_graph=support,
    )
    for atom in trajectory_atoms:
        atom.metadata["attribution_prior"] = example.soft_labels.get(atom.id, 0.0)
    policy = train_policy([example])

    bundle = BenchmarkBundle(
        task=task,
        trajectory_atoms=trajectory_atoms,
        outcome_atoms=outcome_atoms,
        oracle=oracle,
        certificate=certificate,
        gold_support_atom_ids=support.atom_ids,
    )
    results = run_benchmark(
        {
            "recency": RecencyPolicy(),
            "embedding": EmbeddingSimilarityPolicy(outcome_atoms=outcome_atoms),
            "learned_policy": policy,
        },
        [bundle],
        budgets=[0.25, 0.5, 0.75, 1.0],
    )
    print(f"certificate cost={certificate.cost} support_atoms={len(support.atom_ids)}")
    print(format_benchmark(results))


if __name__ == "__main__":
    main()
