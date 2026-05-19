from core.atoms import Atom, OutcomeAtom, count_tokens


def test_count_tokens_minimum_one():
    assert count_tokens("") == 1
    assert count_tokens("hello") == 1
    assert count_tokens("hello world foo") == 3


def test_atom_create_computes_tokens():
    a = Atom.create("a1", "t", "s", "observation", "alpha beta gamma")
    assert a.token_count == 3
    assert a.atom_type == "observation"
    assert a.metadata == {}


def test_outcome_atom_create_carries_oracle_fields():
    o = OutcomeAtom.create(
        "o1",
        "t",
        None,
        "outcome_atom",
        "the answer is 42",
        oracle_relevance_score=0.7,
        necessary=True,
    )
    assert o.oracle_relevance_score == 0.7
    assert o.necessary is True
    assert o.atom_type == "outcome_atom"
