import logging

from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus
from app.events.schemas import ThoughtCreated
from app.sparring.llm import run_spar
from app.sparring.retrieval import retrieve_context
from app.sparring.router import route_sparring_result

log = logging.getLogger(__name__)


class SparringEngine:
    def __init__(
        self,
        *,
        cfg: LLMConfig,
        nodes: NodeRepository,
        edges: EdgeRepository,
        vec: VectorStore,
        bus: EventBus,
        embedder: EmbeddingsProvider,
        top_k: int = 12,
        depth: int = 2,
    ):
        self.cfg = cfg
        self.nodes = nodes
        self.edges = edges
        self.vec = vec
        self.bus = bus
        self.embedder = embedder
        self.top_k = top_k
        self.depth = depth

    def attach(self) -> None:
        self.bus.subscribe("thought.created", self._handle_thought_created)

    async def _handle_thought_created(self, event: ThoughtCreated) -> None:
        try:
            embedding = await self.embedder.embed(event.content)
            context = retrieve_context(
                query_embedding=embedding,
                top_k=self.top_k,
                depth=self.depth,
                vec=self.vec,
                conn=self.nodes.conn,
                exclude_ids=frozenset({event.thought_id}),
            )
            result = await run_spar(
                cfg=self.cfg,
                thought_content=event.content,
                context_bundle=context,
            )
            await route_sparring_result(
                result=result,
                thought_id=event.thought_id,
                nodes=self.nodes,
                edges=self.edges,
                bus=self.bus,
                conn=self.nodes.conn,
            )
        except Exception:
            log.exception("Sparring failed for thought %s", event.thought_id)
