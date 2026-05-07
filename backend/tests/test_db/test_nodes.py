from pathlib import Path

import pytest
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, ThoughtNode


@pytest.fixture
def conn(tmp_path: Path) -> KuzuConnection:
    db_path = tmp_path / "test.kuzu"
    c = KuzuConnection(str(db_path))
    c.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    c.bootstrap_schema(schema_dir)
    yield c
    c.close()


def test_create_and_get_thought(conn: KuzuConnection):
    repo = NodeRepository(conn)
    thought = ThoughtNode(content="hello", source="cli")
    repo.create(thought)
    fetched = repo.get(thought.id, "Thought")
    assert fetched["id"] == thought.id
    assert fetched["content"] == "hello"
    assert fetched["source"] == "cli"


def test_create_bet_with_vault_pointer(conn: KuzuConnection):
    repo = NodeRepository(conn)
    bet = BetNode(
        slug="auth_pivot",
        title="Pivot",
        vault_path="Brain/Bets/bet_auth_pivot.md",
        owner="cto",
    )
    repo.create(bet)
    fetched = repo.get(bet.id, "Bet")
    assert fetched["vault_path"] == "Brain/Bets/bet_auth_pivot.md"


def test_get_missing_returns_none(conn: KuzuConnection):
    repo = NodeRepository(conn)
    assert repo.get("nonexistent", "Thought") is None


def test_create_and_get_agent_firing(conn: KuzuConnection):
    from app.db.schemas import AgentFiringNode

    repo = NodeRepository(conn)
    firing = AgentFiringNode(agent_id="engineer-1", trace_id="trace_abc")
    repo.create(firing)
    fetched = repo.get(firing.id, "AgentFiring")
    assert fetched["id"] == firing.id
    assert fetched["agent_id"] == "engineer-1"
    assert fetched["trace_id"] == "trace_abc"
