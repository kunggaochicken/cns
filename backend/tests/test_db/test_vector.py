from pathlib import Path

from app.db.vector import VectorStore


def test_upsert_and_search(tmp_path: Path):
    db_path = tmp_path / "vec.sqlite"
    store = VectorStore(str(db_path), dim=4)
    store.connect()

    store.upsert("a", [1.0, 0.0, 0.0, 0.0])
    store.upsert("b", [0.0, 1.0, 0.0, 0.0])
    store.upsert("c", [0.9, 0.1, 0.0, 0.0])

    results = store.search([1.0, 0.05, 0.0, 0.0], top_k=2)
    ids = [r["id"] for r in results]
    assert "a" in ids and "c" in ids
    assert "b" not in ids
    store.close()


def test_upsert_replaces_existing(tmp_path: Path):
    db_path = tmp_path / "vec.sqlite"
    store = VectorStore(str(db_path), dim=4)
    store.connect()
    store.upsert("a", [1.0, 0.0, 0.0, 0.0])
    store.upsert("a", [0.0, 1.0, 0.0, 0.0])
    results = store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert results[0]["id"] == "a"
    store.close()
