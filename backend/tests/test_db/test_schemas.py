from datetime import datetime

from app.db.schemas import (
    BetNode,
    EdgeRecord,
    GateItemNode,
    NodeType,
    ThoughtNode,
)


def test_thought_node_round_trip():
    t = ThoughtNode(
        content="should we ship preview?",
        source="pwa",
        metadata={"author": "user"},
    )
    assert t.id is not None
    assert t.node_type == NodeType.THOUGHT
    assert t.content == "should we ship preview?"
    assert isinstance(t.created_at, datetime)


def test_bet_node_with_vault_pointer():
    b = BetNode(
        slug="auth_pivot",
        title="Pivot to OAuth",
        vault_path="Brain/Bets/bet_auth_pivot.md",
        owner="cto",
        horizon="Q",
        confidence="high",
    )
    assert b.node_type == NodeType.BET
    assert b.vault_path == "Brain/Bets/bet_auth_pivot.md"


def test_gate_item_default_unresolved():
    g = GateItemNode(prompt="Ship preview deploy?", urgency="high")
    assert g.resolved_at is None
    assert g.decision is None


def test_edge_record_typed():
    e = EdgeRecord(
        from_id="t_1",
        from_type=NodeType.THOUGHT,
        to_id="b_1",
        to_type=NodeType.BET,
        edge_type="sparred-against",
        confidence=0.82,
    )
    assert e.edge_type == "sparred-against"
    assert e.confidence == 0.82
