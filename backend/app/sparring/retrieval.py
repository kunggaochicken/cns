from app.db.kuzu import KuzuConnection
from app.db.vector import VectorStore

# Tables to search across when locating seed nodes by id
_ALL_TABLES = [
    "Thought",
    "Bet",
    "Task",
    "Decision",
    "Conflict",
    "Outcome",
    "AgentFiring",
    "CodeChange",
    "Conversation",
    "Doc",
    "GateItem",
]


def retrieve_context(
    *,
    query_embedding: list[float],
    top_k: int,
    depth: int,
    vec: VectorStore,
    conn: KuzuConnection,
) -> dict:
    """Pull top_k vector matches, then expand graph neighborhood by `depth` hops.

    Returns: {"nodes": [{"id", "table"}, ...], "edges": [{"from_id", "to_id", "edge_type"}, ...]}
    """
    matches = vec.search(query_embedding, top_k=top_k)
    seed_ids = {m["id"] for m in matches}

    # Locate which Kuzu table each seed lives in by querying each table
    seed_nodes: list[dict] = []
    for table in _ALL_TABLES:
        rows = conn.query(
            f"MATCH (n:{table}) WHERE n.id IN $ids RETURN n.id AS id",
            {"ids": list(seed_ids)},
        )
        for row in rows:
            seed_nodes.append({"id": row["id"], "table": table})

    # Expand neighborhood via BFS over REL edges
    visited_ids = set(seed_ids)
    frontier = list(seed_ids)
    expanded_nodes: list[dict] = list(seed_nodes)
    expanded_edges: list[dict] = []

    for _ in range(depth):
        if not frontier:
            break
        next_frontier: list[str] = []
        # Query each table for neighbors. Kuzu's label() function isn't reliable
        # across versions, so we union per-table queries.
        for table in _ALL_TABLES:
            rows = conn.query(
                f"MATCH (a)-[r:REL]-(b:{table}) WHERE a.id IN $ids "
                "RETURN DISTINCT b.id AS id, r.edge_type AS edge_type, a.id AS from_id",
                {"ids": frontier},
            )
            for row in rows:
                if row["id"] in visited_ids:
                    continue
                visited_ids.add(row["id"])
                expanded_nodes.append({"id": row["id"], "table": table})
                expanded_edges.append(
                    {
                        "from_id": row["from_id"],
                        "to_id": row["id"],
                        "edge_type": row["edge_type"],
                    }
                )
                next_frontier.append(row["id"])
        frontier = next_frontier

    return {"nodes": expanded_nodes, "edges": expanded_edges}
