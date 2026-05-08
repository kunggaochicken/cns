from typing import Literal

from fastapi import APIRouter, Query

from app.db.kuzu import KuzuConnection
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider

# Tables we look up by id after a vector hit, to discover the table name
_VECTOR_LOOKUP_TABLES = (
    "Thought",
    "Bet",
    "Decision",
    "Conflict",
    "Doc",
    "GateItem",
    "CodeChange",
    "Outcome",
    "Conversation",
)

# Tables + content columns for text search
_TEXT_QUERIES: tuple[tuple[str, str], ...] = (
    ("Thought", "content"),
    ("Bet", "title"),
    ("Bet", "slug"),
    ("Decision", "content"),
    ("Doc", "title"),
    ("Conflict", "summary"),
    ("Outcome", "summary"),
)


def build_search_router(
    *,
    conn: KuzuConnection,
    vec: VectorStore,
    embedder: EmbeddingsProvider,
) -> APIRouter:
    router = APIRouter()

    @router.get("/search")
    async def search(
        q: str = Query(..., min_length=1),
        mode: Literal["vector", "text"] = "vector",
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[dict]:
        if mode == "vector":
            embedding = await embedder.embed(q)
            matches = vec.search(embedding, top_k=limit)
            seed_ids = [m["id"] for m in matches]
            if not seed_ids:
                return []
            results: list[dict] = []
            for table in _VECTOR_LOOKUP_TABLES:
                rows = conn.query(
                    f"MATCH (n:{table}) WHERE n.id IN $ids RETURN n.id AS id",
                    {"ids": seed_ids},
                )
                for r in rows:
                    results.append({"id": r["id"], "type": table})
            return results

        # Text mode: case-insensitive substring match on content-bearing columns.
        # Kuzu's CONTAINS is case-sensitive, so we lowercase both sides.
        needle_lc = q.lower()
        results = []
        for table, col in _TEXT_QUERIES:
            rows = conn.query(
                f"MATCH (n:{table}) WHERE LOWER(n.{col}) CONTAINS $needle "
                f"RETURN n.id AS id, n.{col} AS summary LIMIT $limit",
                {"needle": needle_lc, "limit": limit},
            )
            for r in rows:
                results.append(
                    {
                        "id": r["id"],
                        "type": table,
                        "summary": r.get("summary", ""),
                    }
                )
        return results[:limit]

    return router
