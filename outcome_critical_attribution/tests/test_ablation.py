from ablation.beam import beam_minimize_outcome_atoms
from ablation.delta_debugging import ddmin_minimize_outcome_atoms
from ablation.greedy import greedy_minimize_outcome_atoms
from core.atoms import OutcomeAtom
from core.oracle import MockOracle
from core.task import Task


def _scenario():
    task = Task(id="t", domain="d", prompt="q")
    atoms = [
        OutcomeAtom.create("o1", "t", None, "outcome_atom", "alpha keyword present here"),
        OutcomeAtom.create("o2", "t", None, "outcome_atom", "unrelated filler text one"),
        OutcomeAtom.create("o3", "t", None, "outcome_atom", "beta keyword also here"),
        OutcomeAtom.create("o4", "t", None, "outcome_atom", "more filler unrelated"),
    ]
    oracle = MockOracle(required_keywords=["alpha", "beta"])
    return task, atoms, oracle


def test_greedy_drops_irrelevant_outcome_atoms():
    task, atoms, oracle = _scenario()
    cert = greedy_minimize_outcome_atoms(task, atoms, oracle)
    assert set(cert.outcome_atom_ids) == {"o1", "o3"}
    assert cert.oracle_score == 1.0
    assert cert.cost > 0


def test_greedy_initial_failure_returns_full_set():
    task, atoms, _ = _scenario()
    impossible = MockOracle(required_keywords=["zzz"])
    cert = greedy_minimize_outcome_atoms(task, atoms, impossible)
    assert cert.metadata["initial_success"] is False
    assert set(cert.outcome_atom_ids) == {a.id for a in atoms}


def test_beam_finds_minimal_certificate():
    task, atoms, oracle = _scenario()
    cert = beam_minimize_outcome_atoms(task, atoms, oracle, beam_width=2)
    assert set(cert.outcome_atom_ids) == {"o1", "o3"}


def test_ddmin_finds_minimal_certificate():
    task, atoms, oracle = _scenario()
    cert = ddmin_minimize_outcome_atoms(task, atoms, oracle)
    assert {"o1", "o3"}.issubset(set(cert.outcome_atom_ids))
    # 1-minimal: no single atom in the certificate is removable.
    for atom_id in cert.outcome_atom_ids:
        smaller = [a for a in atoms if a.id in set(cert.outcome_atom_ids) and a.id != atom_id]
        if not smaller:
            continue
        assert not oracle.evaluate(task, smaller).success or len(smaller) >= len(
            cert.outcome_atom_ids
        )
