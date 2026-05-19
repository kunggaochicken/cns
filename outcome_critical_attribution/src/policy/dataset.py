"""Training data for the context policy.

Each TrainingExample bundles one trajectory's atoms with the supervision
derived from outcome ablation + attribution: hard labels (in the support
graph or not) and soft labels (an attribution-prior probability).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ablation.base import SuccessCertificate
from core.atoms import Atom, OutcomeAtom
from core.graph import AttributionGraph, SupportGraph


@dataclass
class TrainingExample:
    """One supervised example: atoms in, retain/drop labels out."""

    task_id: str
    domain: str
    trajectory_atoms: list[Atom]
    outcome_atoms: list[OutcomeAtom]
    success_certificate: SuccessCertificate
    attribution_graph: AttributionGraph
    support_graph: SupportGraph
    labels: dict[str, int]
    soft_labels: dict[str, float] = field(default_factory=dict)


def labels_from_support_graph(
    trajectory_atoms: list[Atom], support_graph: SupportGraph
) -> dict[str, int]:
    """Hard label per trajectory atom: 1 if in the support graph, else 0."""
    support = set(support_graph.atom_ids)
    return {a.id: int(a.id in support) for a in trajectory_atoms}


def soft_labels_from_graph(
    trajectory_atoms: list[Atom],
    attribution_graph: AttributionGraph,
    certificate: SuccessCertificate,
) -> dict[str, float]:
    """Soft label per atom: max edge weight into any certificate outcome atom.

    This is the attribution prior `p_phi` -- a smoother signal than the hard
    support-graph membership, useful as a KL anchor during training.
    """
    targets = set(certificate.outcome_atom_ids)
    soft: dict[str, float] = {a.id: 0.0 for a in trajectory_atoms}
    for edge in attribution_graph.edges:
        if edge.target_atom_id in targets and edge.source_atom_id in soft:
            soft[edge.source_atom_id] = max(soft[edge.source_atom_id], edge.weight)
    return soft


def build_training_example(
    task_id: str,
    domain: str,
    trajectory_atoms: list[Atom],
    outcome_atoms: list[OutcomeAtom],
    certificate: SuccessCertificate,
    attribution_graph: AttributionGraph,
    support_graph: SupportGraph,
) -> TrainingExample:
    """Assemble a TrainingExample, deriving hard and soft labels."""
    return TrainingExample(
        task_id=task_id,
        domain=domain,
        trajectory_atoms=trajectory_atoms,
        outcome_atoms=outcome_atoms,
        success_certificate=certificate,
        attribution_graph=attribution_graph,
        support_graph=support_graph,
        labels=labels_from_support_graph(trajectory_atoms, support_graph),
        soft_labels=soft_labels_from_graph(trajectory_atoms, attribution_graph, certificate),
    )
