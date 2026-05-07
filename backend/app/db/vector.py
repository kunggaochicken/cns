import sqlite3
from pathlib import Path

import sqlite_vec


class VectorStore:
    def __init__(self, db_path: str, dim: int = 768):
        self.db_path = db_path
        self.dim = dim
        self._conn: sqlite3.Connection | None = None

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
        # sqlite-vec needs delete+insert for "upsert"
        self._conn.execute("DELETE FROM embeddings WHERE id = ?", (id_,))
        self._conn.execute(
            "INSERT INTO embeddings(id, embedding) VALUES (?, ?)",
            (id_, sqlite_vec.serialize_float32(embedding)),
        )
        self._conn.commit()

    def search(self, query: list[float], top_k: int = 12) -> list[dict]:
        if not self._conn:
            raise RuntimeError("Not connected")
        rows = self._conn.execute(
            "SELECT id, distance FROM embeddings "
            "WHERE embedding MATCH ? "
            "ORDER BY distance LIMIT ?",
            (sqlite_vec.serialize_float32(query), top_k),
        ).fetchall()
        return [{"id": id_, "distance": dist} for id_, dist in rows]
