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
    exclude_ids: frozenset[str] = frozenset(),
) -> dict:
    """Pull top_k vector matches, then expand graph neighborhood by `depth` hops.

    Returns: {"nodes": [{"id", "table"}, ...], "edges": [{"from_id", "to_id", "edge_type"}, ...]}

    ``exclude_ids`` — node IDs to strip from the result set and BFS frontier.
    Pass the ID of the thought being processed so it cannot appear as its own
    context (e.g. when the vector store already contains the new thought).
    """
    matches = vec.search(query_embedding, top_k=top_k)
    seed_ids = {m["id"] for m in matches if m["id"] not in exclude_ids}

    # Locate which Kuzu table each seed lives in by querying each table
    seed_nodes: list[dict] = []
    for table in _ALL_TABLES:
        rows = conn.query(
            f"MATCH (n:{table}) WHERE n.id IN $ids RETURN n",
            {"ids": list(seed_ids)},
        )
        for row in rows:
            node = row["n"] if isinstance(row.get("n"), dict) else row
            seed_nodes.append(
                {
                    "id": node.get("id"),
                    "table": table,
                    "summary": _summarize(node, table),
                }
            )

    # Expand neighborhood via BFS over REL edges
    # Seed visited_ids with exclude_ids so we never expand from an excluded node
    visited_ids = set(seed_ids) | set(exclude_ids)
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
                "RETURN DISTINCT b AS b, r.edge_type AS edge_type, a.id AS from_id",
                {"ids": frontier},
            )
            for row in rows:
                b_node = row["b"] if isinstance(row.get("b"), dict) else row
                b_id = b_node.get("id") if isinstance(b_node, dict) else row.get("id")
                if b_id in visited_ids:
                    continue
                visited_ids.add(b_id)
                expanded_nodes.append(
                    {
                        "id": b_id,
                        "table": table,
                        "summary": _summarize(
                            b_node if isinstance(b_node, dict) else {}, table
                        ),
                    }
                )
                expanded_edges.append(
                    {
                        "from_id": row["from_id"],
                        "to_id": b_id,
                        "edge_type": row["edge_type"],
                    }
                )
                next_frontier.append(b_id)
        frontier = next_frontier

    return {"nodes": expanded_nodes, "edges": expanded_edges}


def _summarize(node: dict, table: str) -> str:
    """Build a short human-readable summary of a node for LLM context."""
    if table == "Thought":
        return (node.get("content") or "")[:200]
    if table == "Bet":
        return f"{node.get('title', '')} — {node.get('slug', '')}"
    if table == "Decision":
        return (node.get("content") or "")[:200]
    if table == "Conflict":
        return node.get("summary", "")[:200]
    if table == "GateItem":
        return (node.get("prompt") or "")[:200]
    if table == "Doc":
        return node.get("title", "")
    if table == "Task":
        return node.get("title", "")
    if table == "CodeChange":
        return f"{node.get('repo', '')}@{node.get('sha', '')[:7]}: {node.get('summary', '')}"
    if table == "Outcome":
        return node.get("summary", "")[:200]
    if table == "Conversation":
        return node.get("summary", "")[:200]
    return ""
