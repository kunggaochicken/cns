from attribution.graph_builder import HeuristicAttributor
from core.atoms import Atom, OutcomeAtom
from core.graph import AttributionEdge, AttributionGraph


def _atom(aid, text):
    return Atom.create(aid, "t", "s", "observation", text)


def _outcome(aid, text):
    return OutcomeAtom.create(aid, "t", None, "outcome_atom", text)


def test_upstream_atoms_traverses_transitively():
    atoms = {
        a.id: a
        for a in [
            _atom("a", "alpha"),
            _atom("b", "beta"),
            _atom("c", "gamma"),
            _outcome("y", "final"),
        ]
    }
    edges = [
        AttributionEdge("a", "b", 0.8, "test"),
        AttributionEdge("b", "y", 0.9, "test"),
        AttributionEdge("c", "y", 0.2, "test"),  # below threshold below
    ]
    graph = AttributionGraph(atoms=atoms, edges=edges)
    assert graph.upstream_atoms(["y"]) == {"a", "b", "c"}
    assert graph.upstream_atoms(["y"], min_weight=0.5) == {"a", "b"}


def test_incoming_outgoing_edges():
    atoms = {a.id: a for a in [_atom("a", "x"), _outcome("y", "z")]}
    edges = [AttributionEdge("a", "y", 1.0, "test")]
    graph = AttributionGraph(atoms=atoms, edges=edges)
    assert graph.incoming_edges("y")[0].source_atom_id == "a"
    assert graph.outgoing_edges("a")[0].target_atom_id == "y"


def test_heuristic_attributor_links_related_atoms():
    traj = [_atom("a", "the answer is forty two"), _atom("b", "unrelated weather text")]
    out = [_outcome("y", "answer is forty two")]
    graph = HeuristicAttributor(min_weight=0.1).attribute(traj, out)
    sources = {e.source_atom_id for e in graph.incoming_edges("y")}
    assert "a" in sources
    assert "b" not in sources
