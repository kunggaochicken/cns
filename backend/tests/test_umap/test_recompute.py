from pathlib import Path

import numpy as np
import pytest

from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore
from app.umap.recompute import compute_and_store_umap


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=8)
    vec.connect()
    yield {"conn": conn, "nodes": nodes, "vec": vec}
    vec.close()
    conn.close()


def test_skips_when_too_few_embeddings(stack):
    t = ThoughtNode(content="x", source="cli")
    stack["nodes"].create(t)
    stack["vec"].upsert(t.id, [1.0] + [0.0] * 7)
    n = compute_and_store_umap(conn=stack["conn"], vec=stack["vec"], n_neighbors=15)
    assert n == 0


def test_writes_umap_coords_for_each_thought(stack):
    rng = np.random.default_rng(0)
    ids = []
    for _i in range(30):
        t = ThoughtNode(content=f"thought {_i}", source="cli")
        stack["nodes"].create(t)
        stack["vec"].upsert(t.id, rng.normal(size=8).tolist())
        ids.append(t.id)

    n = compute_and_store_umap(conn=stack["conn"], vec=stack["vec"], n_neighbors=5)
    assert n == 30
    rows = stack["conn"].query(
        "MATCH (t:Thought) WHERE t.umap_x IS NOT NULL RETURN t.id AS id"
    )
    returned_ids = {r["id"] for r in rows}
    assert returned_ids == set(ids)


def test_orphan_embedding_does_not_crash(stack):
    # Embeddings present but no Thought rows — should return 0, not raise.
    rng = np.random.default_rng(1)
    for i in range(10):
        stack["vec"].upsert(f"ghost_{i}", rng.normal(size=8).tolist())
    n = compute_and_store_umap(conn=stack["conn"], vec=stack["vec"], n_neighbors=5)
    assert n == 0
