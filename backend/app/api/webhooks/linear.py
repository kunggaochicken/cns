# backend/app/api/webhooks/linear.py
import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from app.capture.normalizer import normalize_and_persist
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus

log = logging.getLogger(__name__)


def _verify_signature(body: bytes, header_sig: str | None, secret: str) -> bool:
    if not header_sig:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_sig.strip())


def build_linear_webhook_router(
    *,
    nodes: NodeRepository,
    vec: VectorStore,
    bus: EventBus,
    embedder: EmbeddingsProvider,
    secret: str | None,
) -> APIRouter:
    """Build the Linear webhook router.

    If `secret` is None, all requests are rejected with 401 — operators must set
    `webhooks.linear_secret_env` and provision the env var to enable the endpoint.
    """
    router = APIRouter()

    @router.post("/webhooks/linear")
    async def linear_webhook(request: Request):
        body = await request.body()
        sig = request.headers.get("linear-signature")
        if not secret or not _verify_signature(body, sig, secret):
            raise HTTPException(status_code=401, detail="invalid signature")

        payload = await request.json()
        event_type = payload.get("type")
        action = payload.get("action")
        data = payload.get("data", {})

        if event_type != "Issue" or action not in {"create", "update"}:
            return {"status": "ignored"}

        title = data.get("title") or ""
        description = data.get("description") or ""
        content = f"[Linear {action}] {data.get('identifier', '?')}: {title}\n\n{description}".strip()

        metadata = {
            "linear_id": data.get("id"),
            "linear_identifier": data.get("identifier"),
            "linear_team": (data.get("team") or {}).get("key"),
            "linear_url": data.get("url"),
            "linear_action": action,
        }

        thought = await normalize_and_persist(
            content=content,
            source="linear",
            metadata=metadata,
            nodes=nodes,
            vec=vec,
            bus=bus,
            embedder=embedder,
        )
        return {"node_id": thought.id, "status": "sparring"}

    return router
