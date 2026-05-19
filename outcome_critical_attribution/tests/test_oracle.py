from core.atoms import OutcomeAtom
from core.oracle import MockOracle
from core.task import Task


def _atoms(*texts):
    return [
        OutcomeAtom.create(f"o{i}", "t", None, "outcome_atom", txt) for i, txt in enumerate(texts)
    ]


def test_mock_oracle_keyword_success():
    task = Task(id="t", domain="d", prompt="q")
    oracle = MockOracle(required_keywords=["alpha", "beta"])
    result = oracle.evaluate(task, _atoms("alpha lives here", "beta lives there", "filler"))
    assert result.success is True
    assert result.score == 1.0


def test_mock_oracle_reports_missing_keyword():
    task = Task(id="t", domain="d", prompt="q")
    oracle = MockOracle(required_keywords=["alpha", "missing"])
    result = oracle.evaluate(task, _atoms("alpha is present"))
    assert result.success is False
    assert "missing" in result.diagnostics["missing_keywords"]


def test_mock_oracle_required_ids():
    task = Task(id="t", domain="d", prompt="q")
    atoms = _atoms("only one")
    oracle = MockOracle(required_atom_ids=[atoms[0].id])
    assert oracle.evaluate(task, atoms).success is True
    assert oracle.evaluate(task, []).success is False
