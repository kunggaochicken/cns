from pathlib import Path

import pytest

from app.agents.config import AgentSpec, FleetConfig
from app.agents.registry import AgentRegistry
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    yield {"conn": conn, "nodes": NodeRepository(conn)}
    conn.close()


def test_sync_creates_new_agents(stack):
    fleet = FleetConfig(
        agents=[
            AgentSpec(id="cto-1", role="cto", persona="..."),
            AgentSpec(id="engineer-1", role="engineer", persona="..."),
        ]
    )
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(fleet)

    agents = reg.list_agents()
    ids = {a["id"] for a in agents}
    assert ids == {"cto-1", "engineer-1"}


def test_sync_updates_persona_for_existing_agent(stack):
    fleet1 = FleetConfig(agents=[AgentSpec(id="cto-1", role="cto", persona="v1")])
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(fleet1)

    fleet2 = FleetConfig(agents=[AgentSpec(id="cto-1", role="cto", persona="v2")])
    reg.sync(fleet2)

    fetched = reg.get_by_id("cto-1")
    assert fetched["persona"] == "v2"


def test_get_by_role_returns_all_matching(stack):
    fleet = FleetConfig(
        agents=[
            AgentSpec(id="eng-1", role="engineer", persona="a"),
            AgentSpec(id="eng-2", role="engineer", persona="b"),
            AgentSpec(id="cto-1", role="cto", persona="c"),
        ]
    )
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(fleet)

    engineers = reg.get_by_role("engineer")
    assert len(engineers) == 2
