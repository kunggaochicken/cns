import logging

from app.config import DetectorsConfig, LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.detectors.base import Detector
from app.detectors.conflict import ConflictDetector
from app.detectors.duplicate import DuplicateDetector
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus
from app.events.schemas import ThoughtCreated

log = logging.getLogger(__name__)


class SparringEngine:
    """Thin dispatcher that fans `ThoughtCreated` out to typed-edge detectors.

    Replaces the legacy single-LLM sparring path. Each detector owns one edge
    type, runs incrementally on every capture, and has its own bounded
    LLM budget — no batched re-clustering, no clusters-as-atoms.
    """

    def __init__(
        self,
        *,
        cfg: LLMConfig,
        detectors_cfg: DetectorsConfig,
        conn: KuzuConnection,
        nodes: NodeRepository,
        edges: EdgeRepository,
        vec: VectorStore,
        bus: EventBus,
        embedder: EmbeddingsProvider,
        vault_path: str,
    ):
        self.bus = bus
        self.embedder = embedder
        self.detectors: list[Detector] = []
        if detectors_cfg.duplicate_enabled:
            self.detectors.append(DuplicateDetector(conn=conn, edges=edges, vec=vec))
        if detectors_cfg.conflict_enabled:
            self.detectors.append(
                ConflictDetector(
                    llm_cfg=cfg,
                    conn=conn,
                    nodes=nodes,
                    edges=edges,
                    vec=vec,
                    bus=bus,
                    vault_path=vault_path,
                )
            )

    def attach(self) -> None:
        self.bus.subscribe("thought.created", self._handle_thought_created)

    async def _handle_thought_created(self, event: ThoughtCreated) -> None:
        try:
            embedding = await self.embedder.embed(event.content)
        except Exception:
            log.exception(
                "embed failed for %s; skipping detector dispatch", event.thought_id
            )
            return

        for detector in self.detectors:
            try:
                outcome = await detector.run(
                    thought_id=event.thought_id,
                    content=event.content,
                    embedding=embedding,
                )
                log.info(
                    "detector=%s thought=%s candidates=%d edges=%d nodes=%d",
                    outcome.detector,
                    outcome.thought_id,
                    outcome.candidates_examined,
                    outcome.edges_written,
                    outcome.nodes_written,
                )
            except Exception:
                log.exception(
                    "detector %s failed for %s", detector.name, event.thought_id
                )
