from pathlib import Path

import numpy as np
from click.testing import CliRunner

from app.cli.agents import cli
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore


def test_recompute_cli_writes_coords(tmp_path: Path, monkeypatch):
    kuzu_path = tmp_path / "g.kuzu"
    vec_path = tmp_path / "g-vec.sqlite"
    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text(
        f"db:\n  kuzu_path: {kuzu_path}\n  vector_path: {vec_path}\n"
        "embeddings:\n  provider: ollama\n  model: nomic-embed-text\n"
    )
    monkeypatch.setenv("GIGABRAIN_CONFIG", str(cfg_path))

    # Seed DB + vector store with enough thoughts to clear the n_neighbors gate
    conn = KuzuConnection(str(kuzu_path))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    vec = VectorStore(str(vec_path), dim=8)
    vec.connect()
    rng = np.random.default_rng(0)
    for i in range(20):
        t = ThoughtNode(content=f"t {i}", source="cli")
        nodes.create(t)
        vec.upsert(t.id, rng.normal(size=8).tolist())
    vec.close()
    conn.close()

    # Stub build_provider so the CLI doesn't try to hit Ollama
    from app.embeddings import factory

    class _Stub:
        dim = 8

    monkeypatch.setattr(factory, "build_provider", lambda _cfg: _Stub())

    runner = CliRunner()
    result = runner.invoke(cli, ["umap", "recompute", "--n-neighbors", "5"])
    assert result.exit_code == 0, result.output
    assert "updated" in result.output
