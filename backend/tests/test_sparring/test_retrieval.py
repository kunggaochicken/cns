from pathlib import Path

import pytest
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, EdgeRecord, NodeType
from app.db.vector import VectorStore
from app.sparring.retrieval import retrieve_context


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    yield {"conn": conn, "nodes": nodes, "edges": edges, "vec": vec}
    vec.close()
    conn.close()


def test_retrieve_pulls_top_k_and_neighbors(stack):
    nodes, edges, vec = stack["nodes"], stack["edges"], stack["vec"]

    bet = BetNode(slug="auth", title="Auth pivot", vault_path="x.md", owner="cto")
    other = BetNode(slug="ui", title="UI redesign", vault_path="y.md", owner="cto")
    nodes.create(bet)
    nodes.create(other)
    vec.upsert(bet.id, [1.0, 0.0, 0.0, 0.0])
    vec.upsert(other.id, [0.0, 1.0, 0.0, 0.0])

    edges.create(
        EdgeRecord(
            from_id=bet.id,
            from_type=NodeType.BET,
            to_id=other.id,
            to_type=NodeType.BET,
            edge_type="related-to",
        )
    )

    query_vec = [0.95, 0.05, 0.0, 0.0]
    result = retrieve_context(
        query_embedding=query_vec,
        top_k=1,
        depth=1,
        vec=vec,
        conn=stack["conn"],
    )
    ids = {n["id"] for n in result["nodes"]}
    assert bet.id in ids  # nearest
    assert other.id in ids  # depth=1 expansion
