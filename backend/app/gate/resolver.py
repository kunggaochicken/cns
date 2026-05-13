from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from app.db.kuzu import KuzuConnection


class GateResolveRequest(BaseModel):
    decision: Literal["approved", "vetoed", "resteered"]
    reasoning: str = ""
    alternative: str | None = None


def resolve_gate_item(
    conn: KuzuConnection, gate_id: str, req: GateResolveRequest
) -> bool:
    rows = conn.query(
        "MATCH (g:GateItem) WHERE g.id = $id RETURN g.id AS id",
        {"id": gate_id},
    )
    if not rows:
        return False

    conn.query(
        "MATCH (g:GateItem) WHERE g.id = $id "
        "SET g.decision = $decision, g.reasoning = $reasoning, "
        "g.resolved_at = $resolved_at",
        {
            "id": gate_id,
            "decision": req.decision,
            "reasoning": req.reasoning,
            "resolved_at": datetime.now(UTC),
        },
    )
    return True
