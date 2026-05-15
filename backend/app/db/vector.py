import math
import sqlite3
import threading
from pathlib import Path

import sqlite_vec


def _normalize(vec: list[float]) -> list[float]:
    """Scale a vector to unit length. Ollama embeddings (nomic-embed-text) are
    not normalized — raw magnitudes run ~14-20 — so L2 distance between two
    embeddings has no fixed relationship to cosine similarity. Normalizing on
    write and on query makes sqlite-vec's L2 distance a pure function of the
    angle: distance == sqrt(2 * (1 - cos)). The detector thresholds depend on
    this identity. A zero vector is returned unchanged (cannot be normalized).
    """
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


class VectorStore:
    def __init__(self, db_path: str, dim: int = 768):
        self.db_path = db_path
        self.dim = dim
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS embeddings USING vec0("
            f"id TEXT PRIMARY KEY, embedding FLOAT[{self.dim}])"
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def upsert(self, id_: str, embedding: list[float]) -> None:
        if not self._conn:
            raise RuntimeError("Not connected")
        if len(embedding) != self.dim:
            raise ValueError(f"Expected dim {self.dim}, got {len(embedding)}")
        normalized = _normalize(embedding)
        with self._lock:
            self._conn.execute("DELETE FROM embeddings WHERE id = ?", (id_,))
            self._conn.execute(
                "INSERT INTO embeddings(id, embedding) VALUES (?, ?)",
                (id_, sqlite_vec.serialize_float32(normalized)),
            )
            self._conn.commit()

    def search(self, query: list[float], top_k: int = 12) -> list[dict]:
        if not self._conn:
            raise RuntimeError("Not connected")
        normalized = _normalize(query)
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, distance FROM embeddings "
                "WHERE embedding MATCH ? "
                "ORDER BY distance LIMIT ?",
                (sqlite_vec.serialize_float32(normalized), top_k),
            ).fetchall()
        return [{"id": id_, "distance": dist} for id_, dist in rows]
