"""End-to-end pipeline on a tiny research-agent trajectory.

Run:  python src/examples/toy_research_agent.py
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
from evaluation.baselines import (
    EmbeddingSimilarityPolicy,
    RandomPolicy,
    RecencyPolicy,
    TokenOverlapPolicy,
)
from evaluation.benchmark import BenchmarkBundle, format_benchmark, run_benchmark
from policy.dataset import build_training_example
from policy.train import train_policy


def build_trajectory() -> Trajectory:
    steps = [
        TrajectoryStep(
            id="s0",
            index=0,
            step_type="user_message",
            content=(
                "What year did the IPCC publish its sixth assessment report and who chaired it?"
            ),
        ),
        TrajectoryStep(
            id="s1",
            index=1,
            step_type="plan",
            content=(
                "Search for IPCC AR6 publication year. Then look up the chair of IPCC during AR6."
            ),
        ),
        TrajectoryStep(
            id="s2",
            index=2,
            step_type="tool_call",
            content="web_search(query='IPCC sixth assessment report year published')",
        ),
        TrajectoryStep(
            id="s3",
            index=3,
            step_type="tool_result",
            content=(
                "IPCC AR6 Synthesis Report was published in 2023.\n"
                "Earlier working group contributions appeared in 2021 and 2022."
            ),
        ),
        TrajectoryStep(
            id="s4",
            index=4,
            step_type="tool_call",
            content="web_search(query='IPCC chair 2023 sixth assessment report')",
        ),
        TrajectoryStep(
            id="s5",
            index=5,
            step_type="tool_result",
            content=(
                "Hoesung Lee chaired the IPCC during the sixth assessment cycle, ending in 2023."
            ),
        ),
        TrajectoryStep(
            id="s6",
            index=6,
            step_type="observation",
            content=(
                "Side note: unrelated news article about a new climate satellite launched in 2024."
            ),
        ),
        TrajectoryStep(
            id="s7",
            index=7,
            step_type="final_response",
            content=(
                "The IPCC sixth assessment report's synthesis was published in 2023, "
                "and Hoesung Lee chaired the IPCC during that cycle. "
                "An unrelated climate satellite was launched in 2024."
            ),
        ),
    ]
    outcome = Outcome(
        id="o-research",
        task_id="t-research",
        domain="research",
        content=(
            "The IPCC AR6 synthesis report was published in 2023. "
            "Hoesung Lee chaired the IPCC during the AR6 cycle. "
            "A new climate satellite launched in 2024 (unrelated)."
        ),
    )
    return Trajectory(
        id="traj-research",
        task_id="t-research",
        domain="research",
        steps=steps,
        final_outcome=outcome,
    )


def main() -> None:
    trajectory = build_trajectory()
    task = Task(id=trajectory.task_id, domain="research", prompt=trajectory.steps[0].content)
    atomizer = GenericAtomizer()
    trajectory_atoms = atomizer.atomize_trajectory(trajectory)
    outcome_atoms = atomizer.atomize_outcome(trajectory.final_outcome)

    oracle = MockOracle(required_keywords=["2023", "hoesung lee"])
    certificate = GreedyAblator().minimize(task, outcome_atoms, oracle)
    print(f"certificate cost={certificate.cost} ids={certificate.outcome_atom_ids}")

    graph = HeuristicAttributor().attribute(trajectory_atoms, outcome_atoms)
    support = extract_topk_support(graph, certificate, k_per_outcome=3)
    print(f"support graph has {len(support.atom_ids)} atoms over {len(trajectory_atoms)} total")

    example = build_training_example(
        task_id=task.id,
        domain="research",
        trajectory_atoms=trajectory_atoms,
        outcome_atoms=outcome_atoms,
        certificate=certificate,
        attribution_graph=graph,
        support_graph=support,
    )
    # Decorate each atom with its prior so HeuristicPolicy / features can use it.
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
            "random": RandomPolicy(),
            "recency": RecencyPolicy(),
            "token_overlap": TokenOverlapPolicy(outcome_atoms=outcome_atoms),
            "embedding": EmbeddingSimilarityPolicy(outcome_atoms=outcome_atoms),
            "learned_policy": policy,
        },
        [bundle],
        budgets=[0.25, 0.5, 0.75, 1.0],
    )
    print()
    print(format_benchmark(results))


if __name__ == "__main__":
    main()
