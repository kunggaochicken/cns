import os
from pathlib import Path

import click

from app.config import GigaBrainConfig, load_config
from app.db.kuzu import KuzuConnection
from app.db.vector import VectorStore
from app.embeddings.factory import build_provider
from app.umap.recompute import compute_and_store_umap


@click.group("umap")
def umap_group():
    """UMAP coordinate maintenance for the brain-view frontend."""


@umap_group.command("recompute")
@click.option("--n-neighbors", default=15, show_default=True, type=int)
@click.option("--min-dist", default=0.1, show_default=True, type=float)
def recompute(n_neighbors: int, min_dist: float):
    """Recompute 2D UMAP coords for every Thought with an embedding."""
    path = os.environ.get("GIGABRAIN_CONFIG", "gigabrain.yaml")
    cfg: GigaBrainConfig = (
        load_config(path) if Path(path).exists() else GigaBrainConfig()
    )
    conn = KuzuConnection(cfg.db.kuzu_path)
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    embedder = build_provider(cfg.embeddings)
    vec = VectorStore(cfg.db.vector_path, dim=embedder.dim)
    vec.connect()
    try:
        n = compute_and_store_umap(
            conn=conn, vec=vec, n_neighbors=n_neighbors, min_dist=min_dist
        )
        click.echo(f"updated {n} thoughts")
    finally:
        vec.close()
        conn.close()
