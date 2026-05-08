from pathlib import Path

import pytest
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, EdgeRecord, NodeType, ThoughtNode


@pytest.fixture
def conn(tmp_path: Path) -> KuzuConnection:
    db_path = tmp_path / "test.kuzu"
    c = KuzuConnection(str(db_path))
    c.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    c.bootstrap_schema(schema_dir)
    yield c
    c.close()


def test_create_edge_between_thought_and_bet(conn: KuzuConnection):
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)

    thought = ThoughtNode(content="pivot to oauth", source="cli")
    bet = BetNode(slug="auth_pivot", title="Pivot", vault_path="x.md", owner="cto")
    nodes.create(thought)
    nodes.create(bet)

    edge = EdgeRecord(
        from_id=thought.id,
        from_type=NodeType.THOUGHT,
        to_id=bet.id,
        to_type=NodeType.BET,
        edge_type="sparred-against",
        confidence=0.9,
    )
    edges.create(edge)

    found = edges.list_outgoing(thought.id, "Thought")
    assert len(found) == 1
    assert found[0]["edge_type"] == "sparred-against"
    assert found[0]["to_id"] == bet.id
