import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent

from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ConflictNode, EdgeRecord, NodeType
from app.db.vector import VectorStore
from app.detectors.base import DetectorOutcome
from app.detectors.llm_clients import (
    ConflictVerdict,
    build_conflict_agent,
    conflict_user_message,
)
from app.detectors.sidecar import write_conflict_sidecar
from app.events.bus import EventBus
from app.events.schemas import GraphChanged

log = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5
# sqlite-vec L2 distance on unit-normalized vectors: L2 == sqrt(2 * (1 - cos)).
# Contradictions are often topically related but lexically opposite, landing
# mid-range in embedding space (e.g. "ship monday" vs "delay a month" ≈ cos 0.7,
# L2 ≈ 0.77). Keep the gate loose — distance <= 0.9 ≈ cos >= 0.60 — so genuine
# conflicts reach the sonnet dialectic check. top_k=5 bounds the LLM spend.
_DEFAULT_DISTANCE_THRESHOLD = 0.9
_DEFAULT_MIN_CONFIDENCE = 0.6


@dataclass
class ConflictConfig:
    top_k: int = _DEFAULT_TOP_K
    distance_threshold: float = _DEFAULT_DISTANCE_THRESHOLD
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE


class ConflictDetector:
    name = "conflict"

    def __init__(
        self,
        *,
        llm_cfg: LLMConfig,
        conn: KuzuConnection,
        nodes: NodeRepository,
        edges: EdgeRepository,
        vec: VectorStore,
        bus: EventBus,
        vault_path: str | Path,
        agent: Agent | None = None,
        cfg: ConflictConfig | None = None,
    ):
        self.conn = conn
        self.nodes = nodes
        self.edges = edges
        self.vec = vec
        self.bus = bus
        self.vault_path = Path(vault_path)
        self.agent = agent or build_conflict_agent(llm_cfg)
        self.cfg = cfg or ConflictConfig()

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
                    conflict_user_message(content, cand_content)
                )
                verdict: ConflictVerdict = result.output
            except Exception:
                log.exception("conflict verify failed %s vs %s", thought_id, cand["id"])
                continue
            if not verdict.contradicts or verdict.confidence < self.cfg.min_confidence:
                continue

            # 1. edge: NEW -[contradicts]-> CANDIDATE
            self.edges.create(
                EdgeRecord(
                    from_id=thought_id,
                    from_type=NodeType.THOUGHT,
                    to_id=cand["id"],
                    to_type=NodeType.THOUGHT,
                    edge_type="contradicts",
                    confidence=verdict.confidence,
                )
            )
            outcome.edges_written += 1

            # 2. Conflict node summarizing the contradiction
            conflict = ConflictNode(
                summary=verdict.summary[:200] or "auto-detected contradiction",
                severity="medium",
            )
            self.nodes.create(conflict)
            outcome.nodes_written += 1

            # 3. led-to edge anchoring the new thought to the conflict
            self.edges.create(
                EdgeRecord(
                    from_id=thought_id,
                    from_type=NodeType.THOUGHT,
                    to_id=conflict.id,
                    to_type=NodeType.CONFLICT,
                    edge_type="led-to",
                    confidence=verdict.confidence,
                )
            )
            outcome.edges_written += 1

            # 4. vault sidecar (single-console principle)
            try:
                write_conflict_sidecar(
                    vault_path=self.vault_path,
                    conflict_id=conflict.id,
                    summary=verdict.summary,
                    new_thought_id=thought_id,
                    new_thought_content=content,
                    candidate_thought_id=cand["id"],
                    candidate_thought_content=cand_content,
                    confidence=verdict.confidence,
                )
            except Exception:
                log.exception("conflict sidecar write failed for %s", conflict.id)

            # 5. surface to console
            await self.bus.publish(
                GraphChanged(change_type="node_created", node_id=conflict.id)
            )

        return outcome
