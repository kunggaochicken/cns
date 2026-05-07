from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus
from app.events.schemas import ThoughtCreated


async def normalize_and_persist(
    *,
    content: str,
    source: str,
    metadata: dict,
    nodes: NodeRepository,
    vec: VectorStore,
    bus: EventBus,
    embedder: EmbeddingsProvider,
) -> ThoughtNode:
    embedding = await embedder.embed(content)
    thought = ThoughtNode(content=content, source=source, metadata=metadata)
    nodes.create(thought)
    vec.upsert(thought.id, embedding)
    await bus.publish(ThoughtCreated(thought_id=thought.id, content=content))
    return thought
