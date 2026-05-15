import logging

import numpy as np

from app.db.kuzu import KuzuConnection
from app.db.vector import VectorStore

log = logging.getLogger(__name__)


def _load_all_embeddings(vec: VectorStore) -> tuple[list[str], np.ndarray]:
    """Return (thought_ids, NxD float32 matrix) from the sqlite-vec store.

    We bypass `VectorStore.search` because we want every row, not top-K.
    """
    if vec._conn is None:
        raise RuntimeError("VectorStore not connected")
    ids: list[str] = []
    rows: list[list[float]] = []
    # sqlite-vec stores embeddings as raw little-endian float32 byte blobs
    # (matches sqlite_vec.serialize_float32 on the write path). There is no
    # public deserialize helper, so we decode via numpy directly.
    cursor = vec._conn.execute("SELECT id, embedding FROM embeddings")
    for id_, blob in cursor.fetchall():
        ids.append(id_)
        rows.append(np.frombuffer(blob, dtype=np.float32).tolist())
    if not rows:
        return [], np.zeros((0, 0), dtype=np.float32)
    return ids, np.array(rows, dtype=np.float32)


def compute_and_store_umap(
    *,
    conn: KuzuConnection,
    vec: VectorStore,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    random_state: int = 42,
) -> int:
    """Recompute 2D UMAP coords for every thought with an embedding, and
    persist them as `umap_x` / `umap_y` columns on the `Thought` table.

    Returns the number of thoughts whose coords were updated.

    Skips Thoughts that have no embedding (vec store has nothing for them).
    Returns 0 if fewer than (n_neighbors + 1) embeddings exist.
    """
    import umap  # local import: umap-learn is heavy

    ids, matrix = _load_all_embeddings(vec)
    if matrix.shape[0] < n_neighbors + 1:
        log.info(
            "UMAP skipped: only %d embeddings (need > %d)", matrix.shape[0], n_neighbors
        )
        return 0

    # Restrict to thoughts that exist in Kuzu (skip orphan embeddings)
    existing = {r["id"] for r in conn.query("MATCH (t:Thought) RETURN t.id AS id")}
    keep_idx = [i for i, _id in enumerate(ids) if _id in existing]
    if len(keep_idx) < n_neighbors + 1:
        return 0
    ids = [ids[i] for i in keep_idx]
    matrix = matrix[keep_idx]

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(n_neighbors, len(ids) - 1),
        min_dist=min_dist,
        random_state=random_state,
        metric="cosine",
    )
    coords = reducer.fit_transform(matrix)

    updated = 0
    for tid, (x, y) in zip(ids, coords, strict=True):
        conn.query(
            "MATCH (t:Thought) WHERE t.id = $id SET t.umap_x = $x, t.umap_y = $y",
            {"id": tid, "x": float(x), "y": float(y)},
        )
        updated += 1
    log.info("UMAP recompute wrote coords for %d thoughts", updated)
    return updated
