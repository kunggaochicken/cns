from ablation.base import SuccessCertificate
from attribution.support_extractor import extract_threshold_support, extract_topk_support
from core.atoms import Atom, OutcomeAtom
from core.graph import AttributionEdge, AttributionGraph


def _atom(aid, text):
    return Atom.create(aid, "t", "s", "observation", text)


def _outcome(aid, text):
    return OutcomeAtom.create(aid, "t", None, "outcome_atom", text)


def _setup():
    atoms = {
        a.id: a
        for a in [
            _atom("a", "alpha"),
            _atom("b", "beta"),
            _atom("c", "gamma"),
            _outcome("y1", "result one"),
            _outcome("y2", "result two"),
        ]
    }
    edges = [
        AttributionEdge("a", "y1", 0.9, "test"),
        AttributionEdge("b", "y1", 0.3, "test"),
        AttributionEdge("c", "y2", 0.8, "test"),
        AttributionEdge("a", "b", 0.6, "test"),
    ]
    graph = AttributionGraph(atoms=atoms, edges=edges)
    cert = SuccessCertificate(
        task_id="t",
        outcome_atom_ids=["y1", "y2"],
        oracle_score=1.0,
        cost=10,
    )
    return graph, cert


def test_extract_topk_keeps_topk_per_outcome_and_their_ancestors():
    graph, cert = _setup()
    support = extract_topk_support(graph, cert, k_per_outcome=1)
    # Top-1 incoming for y1 is a (0.9); for y2 is c (0.8). a has no incoming.
    assert set(support.atom_ids) == {"a", "c"}


def test_extract_threshold_filters_weak_edges():
    graph, cert = _setup()
    support = extract_threshold_support(graph, cert, threshold=0.5)
    # b->y1 (0.3) drops out; a->y1 (0.9) and c->y2 (0.8) stay.
    assert "b" not in support.atom_ids
    assert "a" in support.atom_ids and "c" in support.atom_ids
