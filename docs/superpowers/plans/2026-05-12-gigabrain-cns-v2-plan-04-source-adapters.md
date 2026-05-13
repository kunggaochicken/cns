# GigaBrain CNS v2 — Plan 4: Source Adapters (CLI + Webhooks)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three external surfaces that feed thoughts into the spine via the existing `POST /capture` endpoint: a `gigabrain capture "..."` CLI subcommand, a `POST /webhooks/linear` endpoint with HMAC signature verification, and a `POST /webhooks/github` endpoint with `X-Hub-Signature-256` verification. After this plan ships, the brain receives synapse-firings from terminals, Linear ticket events, and GitHub push/PR events — the same pattern as the web app, just different sources.

**Architecture:** Each adapter is a thin translator that maps its source's payload into the `{content, source, metadata}` shape `/capture` expects.

- **CLI** posts HTTPS to a configurable backend URL via `httpx` — runs out-of-process (e.g. on the user's laptop), so HTTP is the only viable wire.
- **Webhooks** mount as FastAPI routers built in `lifespan()` with access to the in-process capture pipeline (`normalize_and_persist`), bypassing the HTTP boundary to avoid double-serialization. Signatures are verified before any work happens; bad signatures return `401` with no DB writes and no logs of payload contents.
- **Config additions** live in `gigabrain.yaml` under new `capture:` and `webhooks:` sections. Secrets are sourced from env vars (`*_env` pattern, mirroring `llm.api_key_env`).

**Tech Stack:** Python 3.11+, FastAPI for the webhook routes, `httpx` for the CLI's HTTP client, `hmac`/`hashlib` from stdlib for signature verification, Click for the CLI subcommand. No new runtime dependencies — `httpx` and `click` are already in `pyproject.toml`.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-gigabrain-cns-v2-design.md`](../specs/2026-05-06-gigabrain-cns-v2-design.md) §2 (Capture pipeline — Source adapters).

**Lessons from Plan 1-3 baked in:**
- `with TestClient(app) as client:` is required for FastAPI lifespan to fire; webhook tests can avoid lifespan by building the router directly (same as `test_capture/test_api.py`).
- Routes that need lifespan-built deps mount via `app.include_router(builder(...))` *inside* `lifespan()`.
- The /capture endpoint is at `/capture` (no `/api` prefix) — the CLI and any external adapters must use that exact path. The frontend learned this the hard way in Plan 3 PR #67.
- Default config paths must be writable without sudo.
- Secrets come from env vars via a `*_env` config key, never inline in YAML.
- `node_type` is a `Literal` discriminator field — adapters do **not** create node types directly; they POST raw `content`+`source`+`metadata` and let the capture pipeline create the `thought` node.

---

## Scope: 3 parallel PRs + 1 foundation PR

This plan is structured as **four sequential-but-mostly-independent PRs**, dispatched in parallel after the foundation lands:

- **PR Foundation** (Tasks 1–2): plan doc + config schema additions (`CaptureClientConfig`, `WebhooksConfig`). Lands first because the other three branch off it. Tiny.
- **PR A — CLI capture** (Tasks 3–6): `gigabrain capture "thought"` subcommand. Independent of webhook work.
- **PR B — Linear webhook** (Tasks 7–10): `/webhooks/linear` with HMAC-SHA256 verification + event→capture mapping.
- **PR C — GitHub webhook** (Tasks 11–14): `/webhooks/github` with `X-Hub-Signature-256` verification + push/PR→capture mapping.
- **Task 15** wires both webhook routers into `lifespan()` and adds a smoke E2E. Goes into whichever of PR B / PR C lands last (or its own tiny follow-up PR if both have already merged).

The three feature PRs each touch disjoint file trees (`app/cli/capture.py`, `app/api/webhooks/linear.py`, `app/api/webhooks/github.py`), so they don't conflict.

---

## File structure

```
backend/
├── gigabrain.yaml.example                # Add `capture:` and `webhooks:` sections
└── app/
    ├── api/
    │   └── webhooks/
    │       ├── __init__.py
    │       ├── linear.py                 # POST /webhooks/linear, HMAC-SHA256 verify
    │       └── github.py                 # POST /webhooks/github, X-Hub-Signature-256 verify
    ├── cli/
    │   ├── __init__.py                   # already exists
    │   ├── agents.py                     # already exists
    │   └── capture.py                    # `gigabrain capture "..."` subcommand
    └── config.py                         # Add CaptureClientConfig, WebhooksConfig

tests/
├── test_api/
│   └── test_webhooks/
│       ├── __init__.py
│       ├── test_linear.py
│       └── test_github.py
└── test_cli/
    ├── __init__.py                       # already exists (from Plan 2)
    └── test_capture.py
```

The CLI subcommand is registered by extending the click group in `app/cli/agents.py` (renaming the module is out of scope — keep the group named `cli` and import the capture command in there).

---

## Task 1: Add `CaptureClientConfig` and `WebhooksConfig` to config schema

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/gigabrain.yaml.example`
- Modify: `backend/tests/test_config.py`

**Why:** The CLI needs to know which backend URL to POST to. The webhooks need their HMAC secrets sourced from env vars. Adding both at once keeps the foundation PR small and unblocks the three feature PRs.

- [ ] **Step 1: Write failing test for the new config sections**

Add to `backend/tests/test_config.py`:

```python
def test_loads_capture_and_webhooks_sections(tmp_path):
    from app.config import load_config

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text(
        "capture:\n"
        "  backend_url: http://localhost:8000\n"
        "webhooks:\n"
        "  linear_secret_env: LINEAR_WEBHOOK_SECRET\n"
        "  github_secret_env: GITHUB_WEBHOOK_SECRET\n"
    )
    cfg = load_config(cfg_path)
    assert cfg.capture.backend_url == "http://localhost:8000"
    assert cfg.webhooks.linear_secret_env == "LINEAR_WEBHOOK_SECRET"
    assert cfg.webhooks.github_secret_env == "GITHUB_WEBHOOK_SECRET"


def test_capture_and_webhooks_default_when_omitted():
    from app.config import GigaBrainConfig

    cfg = GigaBrainConfig()
    assert cfg.capture.backend_url == "http://localhost:8000"
    assert cfg.webhooks.linear_secret_env is None
    assert cfg.webhooks.github_secret_env is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_config.py -v -k "capture or webhooks"`
Expected: FAIL — `cfg.capture` / `cfg.webhooks` don't exist.

- [ ] **Step 3: Add the config classes**

Edit `backend/app/config.py`, add new classes and wire them into `GigaBrainConfig`:

```python
class CaptureClientConfig(BaseModel):
    backend_url: str = "http://localhost:8000"
    timeout_seconds: float = 5.0


class WebhooksConfig(BaseModel):
    linear_secret_env: str | None = None
    github_secret_env: str | None = None


class GigaBrainConfig(BaseModel):
    db: DBConfig = DBConfig()
    embeddings: EmbeddingsConfig = EmbeddingsConfig()
    llm: LLMConfig = LLMConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    gigaflow: GigaFlowConfig = GigaFlowConfig()
    agents: AgentsConfig = AgentsConfig()
    capture: CaptureClientConfig = CaptureClientConfig()
    webhooks: WebhooksConfig = WebhooksConfig()
```

- [ ] **Step 4: Update `gigabrain.yaml.example`**

Append:

```yaml
capture:
  backend_url: http://localhost:8000
  timeout_seconds: 5.0

webhooks:
  # Set env var names that hold the HMAC secrets configured in Linear/GitHub.
  # Leave null to disable webhook signature verification (only safe for local dev).
  linear_secret_env: null
  github_secret_env: null
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_config.py -v`
Expected: PASS — both new tests plus all existing config tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/gigabrain.yaml.example backend/tests/test_config.py
git commit -m "feat(config): add CaptureClientConfig + WebhooksConfig sections

For Plan 4 — CLI capture needs backend_url; webhooks need HMAC secret env-var names."
```

---

## Task 2: Land plan doc + foundation config PR

**Files:**
- New: `docs/superpowers/plans/2026-05-12-gigabrain-cns-v2-plan-04-source-adapters.md` (this file)

- [ ] **Step 1: Stage and commit plan doc**

```bash
git add docs/superpowers/plans/2026-05-12-gigabrain-cns-v2-plan-04-source-adapters.md
git commit -m "docs(plan-04): source adapters implementation plan"
```

- [ ] **Step 2: Push branch and open foundation PR**

```bash
git push -u origin feat/plan-04-adapters
gh pr create --title "feat(plan-04): foundation — plan doc + config additions" \
  --body "$(cat <<'EOF'
## Summary

- Add Plan 04 (Source Adapters) plan doc.
- Add `CaptureClientConfig` (backend_url, timeout) and `WebhooksConfig` (HMAC secret env-var names) to `gigabrain.yaml` schema.

This is the foundation PR for Plan 04. Three feature PRs (CLI capture, Linear webhook, GitHub webhook) branch from this.

## Test plan

- [x] `pytest backend/tests/test_config.py` passes
EOF
)"
```

---

## Task 3 (PR A — CLI capture): Write failing test for HTTP-backed CLI

**Branch:** `feat/plan-04-cli-capture` off `feat/plan-04-adapters`.

**Files:**
- Create: `backend/tests/test_cli/test_capture.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_cli/test_capture.py
from unittest.mock import patch, MagicMock

from click.testing import CliRunner


def test_capture_posts_thought_to_backend(tmp_path):
    from app.cli.agents import cli

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text(
        "capture:\n"
        "  backend_url: http://localhost:9999\n"
        "  timeout_seconds: 2.0\n"
    )

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"node_id": "t_abc123", "status": "sparring"}

    with patch("app.cli.capture.httpx.post", return_value=fake_response) as mock_post:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["capture", "should we ship preview?", "--config", str(cfg_path)],
        )

    assert result.exit_code == 0, result.output
    assert "t_abc123" in result.output
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:9999/capture"
    assert kwargs["json"]["content"] == "should we ship preview?"
    assert kwargs["json"]["source"] == "cli"
    assert kwargs["timeout"] == 2.0


def test_capture_passes_metadata_from_flag(tmp_path):
    from app.cli.agents import cli

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text("capture:\n  backend_url: http://localhost:9999\n")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"node_id": "t_xyz", "status": "sparring"}

    with patch("app.cli.capture.httpx.post", return_value=fake_response) as mock_post:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "capture",
                "hello",
                "--config",
                str(cfg_path),
                "--meta",
                "ticket=GIG-42",
                "--meta",
                "channel=#brain",
            ],
        )

    assert result.exit_code == 0, result.output
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["metadata"] == {"ticket": "GIG-42", "channel": "#brain"}


def test_capture_non_2xx_exits_nonzero_and_prints_error(tmp_path):
    from app.cli.agents import cli

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text("capture:\n  backend_url: http://localhost:9999\n")

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.text = "internal error"

    with patch("app.cli.capture.httpx.post", return_value=fake_response):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["capture", "broken", "--config", str(cfg_path)]
        )

    assert result.exit_code != 0
    assert "500" in result.output or "error" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_cli/test_capture.py -v`
Expected: FAIL — `app.cli.capture` module doesn't exist.

---

## Task 4 (PR A): Implement `gigabrain capture` subcommand

**Files:**
- Create: `backend/app/cli/capture.py`
- Modify: `backend/app/cli/agents.py` (register the new command on the `cli` group)

- [ ] **Step 1: Write the implementation**

Create `backend/app/cli/capture.py`:

```python
from pathlib import Path

import click
import httpx

from app.config import load_config


@click.command("capture")
@click.argument("content", nargs=-1, required=True)
@click.option(
    "--config",
    envvar="GIGABRAIN_CONFIG",
    default="gigabrain.yaml",
    help="Path to gigabrain.yaml",
)
@click.option(
    "--meta",
    "metas",
    multiple=True,
    help="Metadata key=value pair (can be supplied multiple times).",
)
@click.option(
    "--source",
    default="cli",
    show_default=True,
    help="Override the source field on the capture (default: cli).",
)
def capture_cmd(content: tuple[str, ...], config: str, metas: tuple[str, ...], source: str):
    """Capture a thought into the GigaBrain spine via the configured backend."""
    cfg = load_config(Path(config))
    metadata: dict[str, str] = {}
    for kv in metas:
        if "=" not in kv:
            raise click.BadParameter(f"--meta expects key=value, got: {kv!r}")
        k, v = kv.split("=", 1)
        metadata[k] = v

    payload = {
        "content": " ".join(content),
        "source": source,
        "metadata": metadata,
    }
    url = cfg.capture.backend_url.rstrip("/") + "/capture"
    response = httpx.post(url, json=payload, timeout=cfg.capture.timeout_seconds)
    if response.status_code // 100 != 2:
        raise click.ClickException(
            f"capture failed: {response.status_code} {response.text[:200]}"
        )
    body = response.json()
    click.echo(f"{body['node_id']} ({body['status']})")
```

Edit `backend/app/cli/agents.py` — after the existing `@cli.command("agents")` block, register the capture command on the same group:

```python
# at top of file, with other imports
from app.cli.capture import capture_cmd

# at bottom of file, just before `if __name__ == "__main__":`
cli.add_command(capture_cmd)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_cli/test_capture.py -v`
Expected: PASS — all three tests.

- [ ] **Step 3: Verify the CLI is discoverable**

Run: `cd backend && uv run gigabrain --help`
Expected output includes both `agents` and `capture` subcommands.

- [ ] **Step 4: Commit**

```bash
git add backend/app/cli/capture.py backend/app/cli/agents.py backend/tests/test_cli/test_capture.py
git commit -m "feat(cli): \`gigabrain capture\` posts a thought to the backend

Maps CLI args to /capture {content, source: 'cli', metadata}. Source override and
repeatable --meta key=value flags supported. HTTP backend URL + timeout come from
gigabrain.yaml's capture: section."
```

---

## Task 5 (PR A): Add CLI smoke test against a real running backend (optional integration)

**Files:**
- Modify: `backend/tests/test_cli/test_capture.py`

- [ ] **Step 1: Add the integration test, gated on httpx + TestClient**

Append to `test_capture.py`:

```python
def test_capture_against_real_capture_router(tmp_path, monkeypatch):
    """End-to-end: CLI → in-process FastAPI app → /capture writes a thought.

    Uses httpx's MockTransport to route CLI requests to a FastAPI ASGI app, so
    we don't need a network port.
    """
    import httpx
    from fastapi import FastAPI
    from unittest.mock import AsyncMock

    from app.capture.api import build_capture_router
    from app.cli import capture as capture_module
    from app.db.kuzu import KuzuConnection
    from app.db.nodes import NodeRepository
    from app.db.vector import VectorStore
    from app.events.bus import EventBus

    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]

    app = FastAPI()
    app.include_router(
        build_capture_router(nodes=nodes, vec=vec, bus=EventBus(), embedder=embedder)
    )

    transport = httpx.ASGITransport(app=app)

    def _post(url, **kwargs):
        # rewrite to a base_url the ASGITransport understands
        with httpx.Client(transport=transport, base_url="http://testserver") as client:
            path = url.split("://", 1)[1].split("/", 1)[1]
            return client.post("/" + path, **kwargs)

    monkeypatch.setattr(capture_module.httpx, "post", _post)

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text("capture:\n  backend_url: http://testserver\n")

    from click.testing import CliRunner

    from app.cli.agents import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["capture", "smoke", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "(sparring)" in result.output

    vec.close()
    conn.close()
```

> **Note for engineer:** if `httpx.ASGITransport` plumbing is fiddly, drop this task — the unit tests in Tasks 3-4 already cover the CLI behaviour. The remaining wire-up is integration territory we'll re-cover in Task 15.

- [ ] **Step 2: Run test**

Run: `cd backend && uv run python -m pytest tests/test_cli/test_capture.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_cli/test_capture.py
git commit -m "test(cli): end-to-end capture smoke via ASGITransport"
```

---

## Task 6 (PR A): Push and open the CLI PR

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feat/plan-04-cli-capture
gh pr create --base feat/plan-04-adapters \
  --title "feat(cli): \`gigabrain capture\` subcommand (Plan 04 PR A)" \
  --body "$(cat <<'EOF'
## Summary

- Add `gigabrain capture "<text>" [--meta key=value]... [--source X]` CLI subcommand.
- Posts to the backend `/capture` endpoint configured under `capture.backend_url`.

## Test plan

- [x] Unit tests cover happy path, metadata flags, non-2xx error handling.
- [x] Optional ASGITransport integration test exercises the real `/capture` router.
EOF
)"
```

---

## Task 7 (PR B — Linear webhook): Write failing test for the Linear webhook handler

**Branch:** `feat/plan-04-linear-webhook` off `feat/plan-04-adapters`.

**Files:**
- Create: `backend/tests/test_api/test_webhooks/__init__.py` (empty)
- Create: `backend/tests/test_api/test_webhooks/test_linear.py`

**Linear's signing scheme:** SHA-256 HMAC of the raw request body, sent in the `linear-signature` header as a lowercase hex digest. See https://linear.app/developers/webhooks#securing-webhooks. We verify with `hmac.compare_digest`.

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_api/test_webhooks/test_linear.py
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks.linear import build_linear_webhook_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus

SECRET = "linear-test-secret"


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def app_and_bus(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[3] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]

    app = FastAPI()
    app.include_router(
        build_linear_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=SECRET
        )
    )
    yield app, bus
    vec.close()
    conn.close()


def test_linear_create_issue_captures_thought(app_and_bus):
    app, _ = app_and_bus
    payload = {
        "action": "create",
        "type": "Issue",
        "data": {
            "id": "lin_123",
            "identifier": "GIG-42",
            "title": "Ship the brain view",
            "description": "Need to land Plan 03 before Friday.",
            "team": {"key": "GIG"},
            "url": "https://linear.app/team/issue/GIG-42",
        },
    }
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={
                "linear-signature": _sign(body),
                "content-type": "application/json",
            },
        )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "sparring"
    assert out["node_id"].startswith("t_")


def test_linear_rejects_invalid_signature(app_and_bus):
    app, _ = app_and_bus
    payload = {"action": "create", "type": "Issue", "data": {"id": "x", "title": "y"}}
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={"linear-signature": "deadbeef", "content-type": "application/json"},
        )
    assert r.status_code == 401


def test_linear_rejects_missing_signature(app_and_bus):
    app, _ = app_and_bus
    payload = {"action": "create", "type": "Issue", "data": {"id": "x", "title": "y"}}
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 401


def test_linear_ignores_non_issue_events(app_and_bus):
    app, _ = app_and_bus
    payload = {"action": "create", "type": "Comment", "data": {"id": "c", "body": "hi"}}
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={"linear-signature": _sign(body), "content-type": "application/json"},
        )
    # 200 with ignored:true keeps Linear from retrying; we just don't capture it.
    assert r.status_code == 200
    assert r.json() == {"status": "ignored"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_api/test_webhooks/test_linear.py -v`
Expected: FAIL — `app.api.webhooks.linear` doesn't exist.

---

## Task 8 (PR B): Implement the Linear webhook router

**Files:**
- Create: `backend/app/api/webhooks/__init__.py` (empty)
- Create: `backend/app/api/webhooks/linear.py`

- [ ] **Step 1: Write the implementation**

```python
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
        content = f"[Linear {action}] {data.get('identifier','?')}: {title}\n\n{description}".strip()

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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_api/test_webhooks/test_linear.py -v`
Expected: PASS — all 4 tests.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/webhooks/__init__.py backend/app/api/webhooks/linear.py \
        backend/tests/test_api/test_webhooks/__init__.py backend/tests/test_api/test_webhooks/test_linear.py
git commit -m "feat(api): POST /webhooks/linear with HMAC-SHA256 verification

Maps Linear Issue create/update events to /capture {source: linear}. Other event
types return 200 ignored to suppress Linear retries. Invalid or missing signature
returns 401 with no DB writes."
```

---

## Task 9 (PR B): Wire the Linear webhook into main lifespan

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_main_lifespan.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_main_lifespan.py`:

```python
def test_linear_webhook_mounted_when_secret_env_set(monkeypatch, tmp_path):
    """When webhooks.linear_secret_env is set and the env var has a value, the
    /webhooks/linear endpoint should be reachable (returns 401 without a signature
    rather than 404)."""
    monkeypatch.setenv("LINEAR_WEBHOOK_SECRET", "test-secret")

    cfg = tmp_path / "g.yaml"
    cfg.write_text(
        f"db:\n"
        f"  kuzu_path: {tmp_path}/k.kuzu\n"
        f"  vector_path: {tmp_path}/v.sqlite\n"
        f"webhooks:\n"
        f"  linear_secret_env: LINEAR_WEBHOOK_SECRET\n"
    )
    monkeypatch.setenv("GIGABRAIN_CONFIG", str(cfg))

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/webhooks/linear", content=b"{}")
        assert r.status_code == 401  # mounted but unsigned
```

- [ ] **Step 2: Run test**

Run: `cd backend && uv run python -m pytest tests/test_main_lifespan.py::test_linear_webhook_mounted_when_secret_env_set -v`
Expected: FAIL — 404, because the router isn't mounted yet.

- [ ] **Step 3: Wire it up in `main.py`**

Inside `lifespan()`, after the existing `app.include_router(build_graph_router(conn))` call, add:

```python
    from app.api.webhooks.linear import build_linear_webhook_router

    linear_secret = (
        os.environ.get(cfg.webhooks.linear_secret_env)
        if cfg.webhooks.linear_secret_env
        else None
    )
    app.include_router(
        build_linear_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=linear_secret
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/test_main_lifespan.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_main_lifespan.py
git commit -m "feat(main): mount Linear webhook router in lifespan

Loads HMAC secret from env var named by webhooks.linear_secret_env. If unset,
router still mounts but rejects all requests (verification fails closed)."
```

---

## Task 10 (PR B): Push and open the Linear webhook PR

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feat/plan-04-linear-webhook
gh pr create --base feat/plan-04-adapters \
  --title "feat(api): POST /webhooks/linear (Plan 04 PR B)" \
  --body "$(cat <<'EOF'
## Summary

- New `POST /webhooks/linear` endpoint with HMAC-SHA256 signature verification.
- Maps Linear Issue create/update events into `/capture { source: 'linear' }`.
- Mounted in `lifespan()` when `webhooks.linear_secret_env` is configured.

## Test plan

- [x] Unit tests cover happy path, invalid signature → 401, missing signature → 401, non-Issue events → 200 ignored.
- [x] Lifespan integration test confirms the endpoint mounts and rejects unsigned requests with 401.
EOF
)"
```

---

## Task 11 (PR C — GitHub webhook): Write failing test for the GitHub webhook handler

**Branch:** `feat/plan-04-github-webhook` off `feat/plan-04-adapters`.

**Files:**
- Create: `backend/tests/test_api/test_webhooks/test_github.py`

**GitHub's signing scheme:** SHA-256 HMAC of the raw request body, sent in the `X-Hub-Signature-256` header as `sha256=<hexdigest>`. See https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries. The event type comes in the `X-GitHub-Event` header.

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_api/test_webhooks/test_github.py
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks.github import build_github_webhook_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus

SECRET = "github-test-secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def app_and_bus(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[3] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]

    app = FastAPI()
    app.include_router(
        build_github_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=SECRET
        )
    )
    yield app, bus
    vec.close()
    conn.close()


def test_github_push_event_captures_thought(app_and_bus):
    app, _ = app_and_bus
    payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "kunggao/gigabrain"},
        "head_commit": {
            "id": "abc123",
            "message": "feat(api): ship the thing",
            "author": {"name": "James"},
        },
    }
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": _sign(body),
                "x-github-event": "push",
                "content-type": "application/json",
            },
        )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "sparring"
    assert out["node_id"].startswith("t_")


def test_github_pull_request_opened_captures_thought(app_and_bus):
    app, _ = app_and_bus
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Add capture CLI",
            "body": "Implements Plan 04 PR A.",
            "html_url": "https://github.com/kunggao/gigabrain/pull/42",
            "user": {"login": "kunggao"},
        },
        "repository": {"full_name": "kunggao/gigabrain"},
    }
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": _sign(body),
                "x-github-event": "pull_request",
                "content-type": "application/json",
            },
        )
    assert r.status_code == 200
    assert r.json()["status"] == "sparring"


def test_github_rejects_invalid_signature(app_and_bus):
    app, _ = app_and_bus
    body = b"{}"
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": "sha256=deadbeef",
                "x-github-event": "push",
            },
        )
    assert r.status_code == 401


def test_github_rejects_missing_signature(app_and_bus):
    app, _ = app_and_bus
    body = b"{}"
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={"x-github-event": "push"},
        )
    assert r.status_code == 401


def test_github_ignores_unhandled_event_types(app_and_bus):
    app, _ = app_and_bus
    body = b"{}"
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": _sign(body),
                "x-github-event": "ping",
            },
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ignored"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_api/test_webhooks/test_github.py -v`
Expected: FAIL — `app.api.webhooks.github` doesn't exist.

---

## Task 12 (PR C): Implement the GitHub webhook router

**Files:**
- Create: `backend/app/api/webhooks/github.py`

- [ ] **Step 1: Write the implementation**

```python
# backend/app/api/webhooks/github.py
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_api/test_webhooks/test_github.py -v`
Expected: PASS — all 5 tests.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/webhooks/github.py backend/tests/test_api/test_webhooks/test_github.py
git commit -m "feat(api): POST /webhooks/github with X-Hub-Signature-256 verification

Handles push and pull_request events. Other event types (including ping) return
200 ignored. Invalid or missing signature returns 401 with no DB writes."
```

---

## Task 13 (PR C): Wire the GitHub webhook into main lifespan

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_main_lifespan.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_main_lifespan.py`:

```python
def test_github_webhook_mounted_when_secret_env_set(monkeypatch, tmp_path):
    monkeypatch.setenv("GH_WEBHOOK_SECRET", "test-secret")

    cfg = tmp_path / "g.yaml"
    cfg.write_text(
        f"db:\n"
        f"  kuzu_path: {tmp_path}/k.kuzu\n"
        f"  vector_path: {tmp_path}/v.sqlite\n"
        f"webhooks:\n"
        f"  github_secret_env: GH_WEBHOOK_SECRET\n"
    )
    monkeypatch.setenv("GIGABRAIN_CONFIG", str(cfg))

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/webhooks/github", content=b"{}", headers={"x-github-event": "ping"})
        assert r.status_code == 401
```

- [ ] **Step 2: Run test**

Run: `cd backend && uv run python -m pytest tests/test_main_lifespan.py::test_github_webhook_mounted_when_secret_env_set -v`
Expected: FAIL — 404.

- [ ] **Step 3: Wire it up**

Inside `lifespan()`, after the Linear-webhook mounting block, add:

```python
    from app.api.webhooks.github import build_github_webhook_router

    github_secret = (
        os.environ.get(cfg.webhooks.github_secret_env)
        if cfg.webhooks.github_secret_env
        else None
    )
    app.include_router(
        build_github_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=github_secret
        )
    )
```

> **If PR B has not merged yet:** the Linear-webhook mount block won't exist in your branch. Add this GitHub block at the same insertion point (after the graph router include). PR B's mount block will land alongside or before this — no conflict expected because both append before the `from app.agents.api import build_agents_router` line.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/test_main_lifespan.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_main_lifespan.py
git commit -m "feat(main): mount GitHub webhook router in lifespan"
```

---

## Task 14 (PR C): Push and open the GitHub webhook PR

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feat/plan-04-github-webhook
gh pr create --base feat/plan-04-adapters \
  --title "feat(api): POST /webhooks/github (Plan 04 PR C)" \
  --body "$(cat <<'EOF'
## Summary

- New `POST /webhooks/github` endpoint with `X-Hub-Signature-256` verification.
- Maps push and pull_request events into `/capture { source: 'github' }`.
- Mounted in `lifespan()` when `webhooks.github_secret_env` is configured.

## Test plan

- [x] Unit tests cover push, pull_request opened, invalid sig → 401, missing sig → 401, ping → 200 ignored.
- [x] Lifespan integration test confirms the endpoint mounts and rejects unsigned requests with 401.
EOF
)"
```

---

## Task 15: End-to-end smoke — all four sources route into the same graph

**Files:**
- Create: `backend/tests/test_e2e/test_all_sources.py`

This task is wave-3 work: run it once Plan 04 PRs A, B, C have all merged to main. It's a single regression test that proves the contract: regardless of source, every captured thought ends up as a `ThoughtNode` with the correct `source` field.

- [ ] **Step 1: Write the E2E test**

```python
# backend/tests/test_e2e/test_all_sources.py
"""Plan 04: every source adapter funnels into /capture identically."""
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks.github import build_github_webhook_router
from app.api.webhooks.linear import build_linear_webhook_router
from app.capture.api import build_capture_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus


@pytest.fixture
def wired_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]

    app = FastAPI()
    app.include_router(
        build_capture_router(nodes=nodes, vec=vec, bus=bus, embedder=embedder)
    )
    app.include_router(
        build_linear_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret="lin-secret"
        )
    )
    app.include_router(
        build_github_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret="gh-secret"
        )
    )

    yield app, nodes
    vec.close()
    conn.close()


def test_all_three_sources_produce_thoughts_with_correct_source(wired_app):
    app, nodes = wired_app

    with TestClient(app) as client:
        r = client.post("/capture", json={"content": "from cli/web", "source": "cli"})
        assert r.status_code == 200

        lin_payload = json.dumps(
            {
                "action": "create",
                "type": "Issue",
                "data": {"id": "L1", "identifier": "GIG-1", "title": "from linear"},
            }
        ).encode()
        lin_sig = hmac.new(b"lin-secret", lin_payload, hashlib.sha256).hexdigest()
        r = client.post(
            "/webhooks/linear",
            content=lin_payload,
            headers={"linear-signature": lin_sig, "content-type": "application/json"},
        )
        assert r.status_code == 200

        gh_payload = json.dumps(
            {
                "ref": "refs/heads/main",
                "repository": {"full_name": "k/g"},
                "head_commit": {"id": "deadbeefcafe", "message": "from github"},
            }
        ).encode()
        gh_sig = (
            "sha256=" + hmac.new(b"gh-secret", gh_payload, hashlib.sha256).hexdigest()
        )
        r = client.post(
            "/webhooks/github",
            content=gh_payload,
            headers={
                "x-hub-signature-256": gh_sig,
                "x-github-event": "push",
                "content-type": "application/json",
            },
        )
        assert r.status_code == 200

    rows = nodes.conn.query("MATCH (t:Thought) RETURN t.source AS source, t.content AS content")
    sources = sorted([r["source"] for r in rows])
    assert sources == ["cli", "github", "linear"]
```

- [ ] **Step 2: Run test**

Run: `cd backend && uv run python -m pytest tests/test_e2e/test_all_sources.py -v`
Expected: PASS.

- [ ] **Step 3: Commit on a small follow-up branch and PR**

```bash
git checkout -b feat/plan-04-e2e
git add backend/tests/test_e2e/test_all_sources.py
git commit -m "test(e2e): all Plan 04 sources land thoughts with correct source field"
git push -u origin feat/plan-04-e2e
gh pr create --base main \
  --title "test(e2e): Plan 04 source adapters smoke (cli/linear/github → /capture)" \
  --body "Single end-to-end regression covering the three Plan 04 source adapters."
```

---

## Done — Plan 04 deliverables

After all four PRs merge:

1. `gigabrain capture "thought"` works from any terminal with a configured `gigabrain.yaml`.
2. Linear can webhook into `POST /webhooks/linear` and Issue events become thoughts.
3. GitHub can webhook into `POST /webhooks/github` and push / PR events become thoughts.
4. All three sources are byte-equivalent to a `POST /capture` from the frontend — same `ThoughtNode`, same downstream sparring, same agent firings.
5. `gigabrain.yaml.example` documents `capture.backend_url`, `webhooks.linear_secret_env`, `webhooks.github_secret_env`.

This finishes the v0.1 source-adapter list except for the Obsidian file-watcher (Plan 05) and docker-compose self-hosting (Plan 06).
