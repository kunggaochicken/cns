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

_HANDLED = {"push", "pull_request"}


def _verify_signature(body: bytes, header_sig: str | None, secret: str) -> bool:
    if not header_sig or not header_sig.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_sig.strip())


def _format_push(payload: dict) -> tuple[str, dict]:
    commit = payload.get("head_commit") or {}
    repo = (payload.get("repository") or {}).get("full_name", "?")
    ref = payload.get("ref", "?")
    message = commit.get("message") or "(no message)"
    sha = commit.get("id", "?")[:12]
    content = f"[GitHub push] {repo} {ref} {sha}: {message}"
    metadata = {
        "github_repo": repo,
        "github_ref": ref,
        "github_sha": commit.get("id"),
        "github_author": (commit.get("author") or {}).get("name"),
        "github_event": "push",
    }
    return content, metadata


def _format_pull_request(payload: dict) -> tuple[str, dict]:
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("full_name", "?")
    action = payload.get("action", "?")
    title = pr.get("title") or "(no title)"
    body = pr.get("body") or ""
    number = pr.get("number", "?")
    content = f"[GitHub PR {action}] {repo}#{number}: {title}\n\n{body}".strip()
    metadata = {
        "github_repo": repo,
        "github_pr_number": number,
        "github_pr_url": pr.get("html_url"),
        "github_pr_author": (pr.get("user") or {}).get("login"),
        "github_event": "pull_request",
        "github_pr_action": action,
    }
    return content, metadata


def build_github_webhook_router(
    *,
    nodes: NodeRepository,
    vec: VectorStore,
    bus: EventBus,
    embedder: EmbeddingsProvider,
    secret: str | None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/github")
    async def github_webhook(request: Request):
        body = await request.body()
        sig = request.headers.get("x-hub-signature-256")
        if not secret or not _verify_signature(body, sig, secret):
            raise HTTPException(status_code=401, detail="invalid signature")

        event = request.headers.get("x-github-event", "")
        if event not in _HANDLED:
            return {"status": "ignored"}

        payload = await request.json()
        if event == "push":
            content, metadata = _format_push(payload)
        else:  # pull_request
            content, metadata = _format_pull_request(payload)

        thought = await normalize_and_persist(
            content=content,
            source="github",
            metadata=metadata,
            nodes=nodes,
            vec=vec,
            bus=bus,
            embedder=embedder,
        )
        return {"node_id": thought.id, "status": "sparring"}

    return router
