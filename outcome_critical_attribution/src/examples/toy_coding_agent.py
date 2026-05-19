"""End-to-end pipeline on a tiny coding-agent trajectory.

Coding is one of many domains the framework supports. The shape of the code
is *identical* to the research and browser examples -- only the contents of
the trajectory and the oracle's required keywords change.

Run:  python src/examples/toy_coding_agent.py
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
    BM25Policy,
    LLMSummaryPolicy,
    RecencyPolicy,
)
from evaluation.benchmark import BenchmarkBundle, format_benchmark, run_benchmark
from policy.dataset import build_training_example
from policy.train import train_policy


def main() -> None:
    steps = [
        TrajectoryStep(
            id="s0",
            index=0,
            step_type="user_message",
            content=(
                "Fix the off-by-one bug in compute_average so it divides by"
                " len(values), not len(values) - 1."
            ),
        ),
        TrajectoryStep(
            id="s1",
            index=1,
            step_type="tool_call",
            content="read_file(path='src/stats.py')",
        ),
        TrajectoryStep(
            id="s2",
            index=2,
            step_type="tool_result",
            content=(
                "def compute_average(values):\n"
                "    total = sum(values)\n"
                "    return total / (len(values) - 1)\n"
            ),
        ),
        TrajectoryStep(
            id="s3",
            index=3,
            step_type="observation",
            content="Function returns NaN-like behavior when len(values) == 1 -- divides by zero.",
        ),
        TrajectoryStep(
            id="s4",
            index=4,
            step_type="plan",
            content="Replace (len(values) - 1) with len(values).",
        ),
        TrajectoryStep(
            id="s5",
            index=5,
            step_type="artifact_edit",
            content=(
                "--- src/stats.py\n"
                "+++ src/stats.py\n"
                "@@\n"
                "-    return total / (len(values) - 1)\n"
                "+    return total / len(values)\n"
            ),
        ),
        TrajectoryStep(
            id="s6",
            index=6,
            step_type="tool_call",
            content="run_tests(path='tests/test_stats.py')",
        ),
        TrajectoryStep(
            id="s7",
            index=7,
            step_type="tool_result",
            content="All 4 tests passed. Coverage report: 92%.",
        ),
        TrajectoryStep(
            id="s8",
            index=8,
            step_type="observation",
            content="Tangent: noticed an unrelated TODO in src/utils.py.",
        ),
        TrajectoryStep(
            id="s9",
            index=9,
            step_type="final_response",
            content=(
                "Edited compute_average to divide by len(values) instead of len(values) - 1. "
                "All tests pass. Saw an unrelated TODO in src/utils.py."
            ),
        ),
    ]
    outcome = Outcome(
        id="o-coding",
        task_id="t-coding",
        domain="coding",
        content=(
            "Patched src/stats.py: compute_average now divides by len(values). "
            "All tests pass. Unrelated TODO observed in src/utils.py."
        ),
    )
    trajectory = Trajectory(
        id="traj-coding",
        task_id="t-coding",
        domain="coding",
        steps=steps,
        final_outcome=outcome,
    )
    task = Task(id=trajectory.task_id, domain="coding", prompt=steps[0].content)

    atomizer = GenericAtomizer()
    trajectory_atoms = atomizer.atomize_trajectory(trajectory)
    outcome_atoms = atomizer.atomize_outcome(outcome)

    oracle = MockOracle(required_keywords=["compute_average", "len(values)", "tests pass"])
    certificate = GreedyAblator().minimize(task, outcome_atoms, oracle)

    graph = HeuristicAttributor().attribute(trajectory_atoms, outcome_atoms)
    support = extract_topk_support(graph, certificate, k_per_outcome=3)
    example = build_training_example(
        task_id=task.id,
        domain="coding",
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
            "bm25": BM25Policy(outcome_atoms=outcome_atoms),
            "llm_summary": LLMSummaryPolicy(),
            "learned_policy": policy,
        },
        [bundle],
        budgets=[0.25, 0.5, 0.75, 1.0],
    )
    print(f"certificate cost={certificate.cost} support_atoms={len(support.atom_ids)}")
    print(format_benchmark(results))


if __name__ == "__main__":
    main()
