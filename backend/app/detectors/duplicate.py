import logging
from dataclasses import dataclass

from pydantic_ai import Agent

from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.schemas import EdgeRecord, NodeType
from app.db.vector import VectorStore
from app.detectors.base import DetectorOutcome
from app.detectors.llm_clients import (
    DuplicateVerdict,
    build_duplicate_agent,
    duplicate_user_message,
)

log = logging.getLogger(__name__)

# Cosine distance threshold from sqlite-vec. sqlite-vec returns L2 distance for
# normalized vectors which approximates 2 * (1 - cos). distance <= 0.16 ≈ cos >= 0.92.
# We filter pre-LLM at this threshold.
_DEFAULT_DISTANCE_THRESHOLD = 0.16
_DEFAULT_TOP_K = 10


@dataclass
class DuplicateConfig:
    top_k: int = _DEFAULT_TOP_K
    distance_threshold: float = _DEFAULT_DISTANCE_THRESHOLD


class DuplicateDetector:
    name = "duplicate"

    def __init__(
        self,
        *,
        conn: KuzuConnection,
        edges: EdgeRepository,
        vec: VectorStore,
        agent: Agent | None = None,
        cfg: DuplicateConfig | None = None,
    ):
        self.conn = conn
        self.edges = edges
        self.vec = vec
        self.agent = agent or build_duplicate_agent()
        self.cfg = cfg or DuplicateConfig()

    def _fetch_thought_content(self, thought_id: str) -> str | None:
        rows = self.conn.query(
            "MATCH (t:Thought) WHERE t.id = $id RETURN t.content AS c",
            {"id": thought_id},
        )
        return rows[0]["c"] if rows else None

    async def run(
        self,
        *,
        thought_id: str,
        content: str,
        embedding: list[float],
    ) -> DetectorOutcome:
        matches = self.vec.search(embedding, top_k=self.cfg.top_k + 1)
        candidates = [
            m
            for m in matches
            if m["id"] != thought_id and m["distance"] <= self.cfg.distance_threshold
        ][: self.cfg.top_k]

        outcome = DetectorOutcome(
            detector=self.name,
            thought_id=thought_id,
            candidates_examined=len(candidates),
        )

        for cand in candidates:
            cand_content = self._fetch_thought_content(cand["id"])
            if not cand_content:
                continue
            try:
                result = await self.agent.run(
                    duplicate_user_message(content, cand_content)
                )
                verdict: DuplicateVerdict = result.output
            except Exception:
                log.exception(
                    "duplicate verify failed for %s vs %s", thought_id, cand["id"]
                )
                continue
            if verdict.relation == "different":
                continue
            edge_type = (
                "duplicate-of" if verdict.relation == "same" else "near-restatement-of"
            )
            self.edges.create(
                EdgeRecord(
                    from_id=thought_id,
                    from_type=NodeType.THOUGHT,
                    to_id=cand["id"],
                    to_type=NodeType.THOUGHT,
                    edge_type=edge_type,
                    confidence=verdict.confidence,
                )
            )
            outcome.edges_written += 1

        return outcome
