import math
from pathlib import Path

from app.db.vector import VectorStore, _normalize


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


def test_normalize_scales_to_unit_length():
    out = _normalize([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in out)), 1.0)
    assert math.isclose(out[0], 0.6) and math.isclose(out[1], 0.8)


def test_normalize_zero_vector_unchanged():
    assert _normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


def test_search_distance_reflects_cosine_after_normalization(tmp_path: Path):
    # Unnormalized inputs with different magnitudes but identical direction
    # must collapse to distance ~0 once the store normalizes them.
    store = VectorStore(str(tmp_path / "vec.sqlite"), dim=4)
    store.connect()
    store.upsert("big", [20.0, 0.0, 0.0, 0.0])
    results = store.search([0.5, 0.0, 0.0, 0.0], top_k=1)
    assert results[0]["id"] == "big"
    assert results[0]["distance"] < 1e-4
    store.close()
