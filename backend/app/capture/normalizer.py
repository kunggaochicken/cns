import hashlib

from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus
from app.events.schemas import GraphChanged, ThoughtCreated


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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
    content_hash = _hash_content(content)
    existing = nodes.find_thought_by_hash(content_hash, source)
    if existing:
        return ThoughtNode.model_validate(existing)

    embedding = await embedder.embed(content)
    thought = ThoughtNode(
        content=content,
        source=source,
        metadata=metadata,
        content_hash=content_hash,
    )
    nodes.create(thought)
    vec.upsert(thought.id, embedding)
    await bus.publish(ThoughtCreated(thought_id=thought.id, content=content))
    await bus.publish(GraphChanged(change_type="node_created", node_id=thought.id))
    return thought
