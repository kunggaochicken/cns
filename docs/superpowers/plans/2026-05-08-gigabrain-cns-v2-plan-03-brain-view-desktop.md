# GigaBrain CNS v2 — Plan 3: Brain View (Desktop)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the desktop web application that renders the GigaBrain graph as a navigable, real-time canvas — the primary surface where the leader sees thoughts/bets/gate items materialize, picks hot spots to focus on, and resolves gate items in place. After this plan ships, you can open `http://localhost:8000` in a browser and see your brain populate live as you capture thoughts.

**Architecture:** A React + TypeScript SPA built with Vite, rendered with Cytoscape.js for the graph canvas and Tailwind for styling. Talks to the existing FastAPI backend through five new REST endpoints + the existing SSE `/stream`. Built artifacts are served by FastAPI at `/` in production; in dev, Vite proxies `/api/*` and `/stream` to the backend on port 8000.

**Tech Stack (frontend):** React 18, TypeScript 5, Vite 5, Tailwind CSS 3, Cytoscape.js 3, Vitest for unit tests, native `EventSource` for SSE, native `fetch` for REST. No state-management library — graph state lives in a single React context kept in sync with SSE events.

**Tech Stack (backend additions):** FastAPI routes only, leveraging existing KuzuDB + EdgeRepository + NodeRepository. No new substrate.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-gigabrain-cns-v2-design.md`](../specs/2026-05-06-gigabrain-cns-v2-design.md) §4 (Brain view UI).

**Lessons from Plans 1 + 2 baked in:**
- pydantic-ai 1.x API (already in use)
- `with TestClient(app) as client:` so FastAPI lifespan fires
- Routes mounted via `app.include_router(builder(...))` *inside* `lifespan()` after deps exist
- Real-Kuzu integration tests for critical query paths (mock-only tests miss DDL bugs)
- Path traversal: use `is_relative_to`, never `str.startswith`
- Async subprocess only — never `subprocess.run` inside `async def`
- VectorStore is shared and uses `threading.Lock` — no read-without-lock paths
- `node_type` is a Pydantic Literal field, not a property — `model_dump(exclude={"node_type"})` before DB writes
- Repo-root `ruff format --check .` differs from backend's local config — keep both clean
- Pre-commit hooks reformat aggressively; accept and re-stage
- Default config paths must be writable without sudo

---

## Scope check — what's in v0.1 (this plan) and what's not

**In v0.1:**
- Graph canvas with node-type coloring, edge rendering, force-directed layout
- Hot spot detection (server-side, simple "edges in last hour" heuristic) + visual glow
- Gate item highlighting + click-to-resolve modal (approve / veto / resteer)
- Node detail side panel
- Capture bar (text only)
- Live SSE updates animating new nodes/edges in
- Frontend served by FastAPI in prod; Vite hot-reload in dev
- Frontend CI (lint + test + build)

**Deferred to v0.2 / later plans:**
- Voice capture (waits for Plan 5 source adapters)
- Mobile-optimized inbox view (Plan 4)
- External zoom-in destinations: Obsidian deep-link, Linear ticket open, GitHub PR open (Plan 5)
- Full-text or semantic search UI (the backend `GET /search` lands here, but the frontend search input ships in v0.2)
- Time-travel scrubber, history navigation
- Agent panel / swap-into-seat UI (the `/agents` endpoints exist, but the UI is v0.2)
- Authentication / multi-user

**Explicit non-goals:**
- Replacing Obsidian/Linear graph views (we render OUR graph state, link out for content)
- Real-time collaboration / shared cursors

---

## File structure

```
frontend/
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   ├── client.ts            # fetch wrapper, typed request helpers
│   │   ├── types.ts             # NodeRow, EdgeRow, GateItem, etc.
│   │   └── stream.ts            # EventSource hook
│   ├── state/
│   │   ├── GraphProvider.tsx    # React context with graph state + SSE wiring
│   │   └── useGraph.ts
│   ├── views/
│   │   ├── BrainView.tsx        # main layout: top bar, canvas, side panel, capture bar
│   │   ├── TopBar.tsx           # title + live counts (gate items, hot spots)
│   │   ├── GraphCanvas.tsx      # Cytoscape integration
│   │   ├── NodeDetail.tsx       # right side panel
│   │   ├── CaptureBar.tsx       # bottom input
│   │   └── GateItemList.tsx     # list of pending gate items
│   ├── components/
│   │   ├── GateItemResolveModal.tsx
│   │   └── HotSpotBadge.tsx
│   ├── styles/
│   │   └── globals.css
│   └── utils/
│       ├── nodeColors.ts        # type → color mapping
│       └── time.ts              # "3m ago" formatting
└── tests/
    ├── api/
    │   ├── client.test.ts
    │   └── stream.test.ts
    ├── state/
    │   └── GraphProvider.test.tsx
    └── views/
        ├── CaptureBar.test.tsx
        ├── GateItemList.test.tsx
        └── GraphCanvas.test.tsx

backend/app/api/
├── graph.py                     # NEW: GET /graph
├── nodes.py                     # NEW: GET /nodes/{table}/{id}
├── gate_items.py                # NEW: GET /gate-items, POST /gate-items/{id}/resolve
├── hotspots.py                  # NEW: GET /hotspots
└── search.py                    # NEW: GET /search

backend/tests/test_api/
├── test_graph.py                # NEW
├── test_nodes_route.py          # NEW (named to avoid collision with test_db/test_nodes.py)
├── test_gate_items.py           # NEW
├── test_hotspots.py             # NEW
└── test_search.py               # NEW

.github/workflows/
└── frontend-ci.yml              # NEW
```

---

# Section A — Backend API expansion (5 tasks)

These endpoints are what the frontend calls. Each is a thin layer over existing repositories.

## Task 1: `GET /graph` — paginated node + edge dump

**Files:**
- Create: `backend/app/api/graph.py`
- Create: `backend/tests/test_api/test_graph.py`
- Modify: `backend/app/main.py` (mount router in lifespan)

The frontend's first paint pulls the full graph (or a paginated chunk if too large) to render Cytoscape. Subsequent updates flow via SSE.

- [ ] **Step 1: failing test**

```python
# backend/tests/test_api/test_graph.py
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.graph import build_graph_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, ThoughtNode


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    nodes.create(BetNode(slug="auth", title="Auth", vault_path="x.md", owner="cto"))
    nodes.create(ThoughtNode(content="hi", source="cli"))
    app = FastAPI()
    app.include_router(build_graph_router(conn=conn))
    yield app
    conn.close()


def test_graph_returns_nodes_and_edges(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body and "edges" in body
    assert len(body["nodes"]) == 2
    types = {n["type"] for n in body["nodes"]}
    assert {"Bet", "Thought"} <= types


def test_graph_filter_by_type(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/graph?types=Bet")
    body = resp.json()
    assert all(n["type"] == "Bet" for n in body["nodes"])
```

- [ ] **Step 2: implementation**

```python
# backend/app/api/graph.py
from fastapi import APIRouter, Query

from app.db.kuzu import KuzuConnection

# Tables we expose to the brain view (Agent excluded — agents have their own /agents endpoint)
_GRAPH_TABLES = [
    "Thought", "Bet", "Task", "Decision", "Conflict", "Outcome",
    "AgentFiring", "CodeChange", "Conversation", "Doc", "GateItem",
]


def build_graph_router(*, conn: KuzuConnection) -> APIRouter:
    router = APIRouter()

    @router.get("/graph")
    def get_graph(
        types: str | None = Query(default=None, description="Comma-separated node types to include"),
        limit: int = Query(default=2000, ge=1, le=10000),
    ) -> dict:
        included = (types.split(",") if types
                    else _GRAPH_TABLES)
        included = [t for t in included if t in _GRAPH_TABLES]

        all_nodes: list[dict] = []
        for table in included:
            rows = conn.query(
                f"MATCH (n:{table}) RETURN n.id AS id, "
                "n.created_at AS created_at LIMIT $limit",
                {"limit": limit},
            )
            for row in rows:
                all_nodes.append({"id": row["id"], "type": table,
                                  "created_at": str(row.get("created_at", ""))})

        edges = conn.query(
            "MATCH (a)-[r:REL]->(b) "
            "RETURN a.id AS from_id, b.id AS to_id, "
            "r.edge_type AS edge_type, r.created_at AS created_at "
            "LIMIT $limit",
            {"limit": limit * 4},
        )
        edge_list = [
            {"from_id": e["from_id"], "to_id": e["to_id"],
             "edge_type": e["edge_type"], "created_at": str(e.get("created_at", ""))}
            for e in edges
        ]
        return {"nodes": all_nodes, "edges": edge_list}

    return router
```

- [ ] **Step 3: mount in main.py**

Inside `lifespan` in `backend/app/main.py`, after the existing `app.include_router(...)` calls:

```python
from app.api.graph import build_graph_router
app.include_router(build_graph_router(conn=conn))
```

- [ ] **Step 4: run tests + commit**

```bash
cd backend && uv run pytest tests/test_api/test_graph.py -v
```
Expected: PASS (2 tests).

```bash
git add backend/app/api/graph.py backend/app/main.py backend/tests/test_api/test_graph.py
git commit -m "feat(api): GET /graph returns nodes and edges, filterable by type"
```

---

## Task 2: `GET /nodes/{table}/{id}` — node detail with neighborhood

**Files:**
- Create: `backend/app/api/nodes.py`
- Create: `backend/tests/test_api/test_nodes_route.py`
- Modify: `backend/app/main.py`

Returns full properties of a node plus its outgoing/incoming edges, for the right-side detail panel.

- [ ] **Step 1: failing test**

```python
# backend/tests/test_api/test_nodes_route.py
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.nodes import build_nodes_router
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, EdgeRecord, NodeType, ThoughtNode


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bet = BetNode(slug="auth", title="Auth", vault_path="x.md", owner="cto")
    thought = ThoughtNode(content="related thought", source="cli")
    nodes.create(bet)
    nodes.create(thought)
    edges.create(EdgeRecord(
        from_id=thought.id, from_type=NodeType.THOUGHT,
        to_id=bet.id, to_type=NodeType.BET,
        edge_type="sparred-against",
    ))
    app = FastAPI()
    app.include_router(build_nodes_router(conn=conn))
    yield {"app": app, "bet": bet, "thought": thought}
    conn.close()


def test_get_node_returns_props_and_edges(configured_app):
    bet = configured_app["bet"]
    client = TestClient(configured_app["app"])
    resp = client.get(f"/nodes/Bet/{bet.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == bet.id
    assert body["type"] == "Bet"
    assert body["props"]["title"] == "Auth"
    # Incoming sparred-against edge from the thought
    assert any(e["edge_type"] == "sparred-against" for e in body["incoming_edges"])


def test_get_unknown_node_returns_404(configured_app):
    client = TestClient(configured_app["app"])
    resp = client.get("/nodes/Bet/missing")
    assert resp.status_code == 404
```

- [ ] **Step 2: implementation**

```python
# backend/app/api/nodes.py
from fastapi import APIRouter, HTTPException

from app.db.kuzu import KuzuConnection

_VALID_TABLES = {
    "Thought", "Bet", "Task", "Decision", "Conflict", "Outcome",
    "AgentFiring", "CodeChange", "Conversation", "Doc", "GateItem", "Agent",
}


def build_nodes_router(*, conn: KuzuConnection) -> APIRouter:
    router = APIRouter()

    @router.get("/nodes/{table}/{node_id}")
    def get_node(table: str, node_id: str) -> dict:
        if table not in _VALID_TABLES:
            raise HTTPException(status_code=400, detail=f"unknown table: {table}")
        rows = conn.query(
            f"MATCH (n:{table}) WHERE n.id = $id RETURN n",
            {"id": node_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"{table}/{node_id} not found")
        node = rows[0]["n"] if isinstance(rows[0].get("n"), dict) else rows[0]

        outgoing = conn.query(
            f"MATCH (a:{table})-[r:REL]->(b) WHERE a.id = $id "
            "RETURN r.edge_type AS edge_type, b.id AS to_id, "
            "r.confidence AS confidence",
            {"id": node_id},
        )
        incoming = conn.query(
            f"MATCH (a)-[r:REL]->(b:{table}) WHERE b.id = $id "
            "RETURN r.edge_type AS edge_type, a.id AS from_id, "
            "r.confidence AS confidence",
            {"id": node_id},
        )
        return {
            "id": node_id,
            "type": table,
            "props": {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                      for k, v in node.items()},
            "outgoing_edges": outgoing,
            "incoming_edges": incoming,
        }

    return router
```

- [ ] **Step 3: mount + tests + commit**

Mount: `app.include_router(build_nodes_router(conn=conn))` in lifespan.

Run: `cd backend && uv run pytest tests/test_api/test_nodes_route.py -v` → PASS (2 tests).

```bash
git add backend/app/api/nodes.py backend/app/main.py backend/tests/test_api/test_nodes_route.py
git commit -m "feat(api): GET /nodes/{table}/{id} with outgoing/incoming edges"
```

---

## Task 3: `GET /gate-items` + `POST /gate-items/{id}/resolve`

**Files:**
- Create: `backend/app/api/gate_items.py`
- Create: `backend/tests/test_api/test_gate_items.py`
- Modify: `backend/app/main.py`

The gate item endpoint serves the bottom-left card list. Resolve writes the decision back to the graph AND emits a `gigabrain.gate.resolved` event for GigaFlow consumption (per spec §5).

- [ ] **Step 1: failing test**

```python
# backend/tests/test_api/test_gate_items.py
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.gate_items import build_gate_items_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import GateItemNode
from app.events.bus import EventBus


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    bus = EventBus()
    g1 = GateItemNode(prompt="ship preview?", urgency="high")
    g2 = GateItemNode(prompt="send email?", urgency="medium")
    nodes.create(g1)
    nodes.create(g2)
    app = FastAPI()
    app.include_router(build_gate_items_router(nodes=nodes, conn=conn, bus=bus))
    yield {"app": app, "g1": g1, "bus": bus}
    conn.close()


def test_list_unresolved_gate_items(configured_app):
    client = TestClient(configured_app["app"])
    resp = client.get("/gate-items")
    body = resp.json()
    assert len(body) == 2
    # Highest urgency first
    assert body[0]["urgency"] == "high"


def test_resolve_writes_decision_and_marks_resolved(configured_app):
    g1 = configured_app["g1"]
    client = TestClient(configured_app["app"])
    resp = client.post(
        f"/gate-items/{g1.id}/resolve",
        json={"decision": "approved", "reasoning": "looks good"},
    )
    assert resp.status_code == 200

    # Now should not appear in unresolved list
    list_resp = client.get("/gate-items")
    ids = {g["id"] for g in list_resp.json()}
    assert g1.id not in ids


def test_resolve_invalid_decision_returns_422(configured_app):
    g1 = configured_app["g1"]
    client = TestClient(configured_app["app"])
    resp = client.post(
        f"/gate-items/{g1.id}/resolve",
        json={"decision": "maybe", "reasoning": "?"},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: implementation**

```python
# backend/app/api/gate_items.py
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.events.bus import EventBus

_URGENCY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "novel": 3, "low": 4}


class ResolveRequest(BaseModel):
    decision: Literal["approved", "vetoed", "resteered"]
    reasoning: str = ""
    alternative: dict | None = None


def build_gate_items_router(
    *, nodes: NodeRepository, conn: KuzuConnection, bus: EventBus,
) -> APIRouter:
    router = APIRouter()

    @router.get("/gate-items")
    def list_gate_items() -> list[dict]:
        rows = conn.query(
            "MATCH (g:GateItem) WHERE g.resolved_at IS NULL "
            "RETURN g.id AS id, g.prompt AS prompt, g.urgency AS urgency, "
            "g.created_at AS created_at"
        )
        rows.sort(key=lambda r: _URGENCY_ORDER.get(r.get("urgency"), 99))
        return [
            {
                "id": r["id"], "prompt": r["prompt"], "urgency": r.get("urgency"),
                "created_at": str(r.get("created_at", "")),
            }
            for r in rows
        ]

    @router.post("/gate-items/{gate_id}/resolve")
    async def resolve(gate_id: str, req: ResolveRequest) -> dict:
        existing = nodes.get(gate_id, "GateItem")
        if existing is None:
            raise HTTPException(status_code=404, detail=f"gate item {gate_id} not found")
        if existing.get("resolved_at"):
            raise HTTPException(status_code=409, detail="gate item already resolved")

        now = datetime.now(timezone.utc)
        conn.query(
            "MATCH (g:GateItem) WHERE g.id = $id "
            "SET g.resolved_at = $resolved_at, g.decision = $decision, "
            "g.reasoning = $reasoning",
            {"id": gate_id, "resolved_at": now,
             "decision": req.decision, "reasoning": req.reasoning},
        )
        # Emit GigaFlow-shaped event (per spec §5)
        # Importing here to avoid circular import at module load
        from app.events.schemas import BaseModel as _BM
        # We don't have a typed pydantic event for this yet — emit a dict-shaped event
        # via the bus. The OTel exporter will pick it up at the trace level (see Plan 6).
        # For v0.1 we just log the resolution as a graph mutation; GigaFlow integration
        # ships in Plan 6 with the proper event type.
        return {"id": gate_id, "decision": req.decision, "resolved_at": str(now)}

    return router
```

Note: the GigaFlow `gigabrain.gate.resolved` event payload is *defined* in the spec but its emission as a typed event lands in **Plan 6** (GigaFlow integration). For Plan 3, resolving a gate item just updates the graph node — the resolution telemetry path is wired later.

- [ ] **Step 3: mount + tests + commit**

Mount: `app.include_router(build_gate_items_router(nodes=nodes, conn=conn, bus=bus))`.

Run: `cd backend && uv run pytest tests/test_api/test_gate_items.py -v` → PASS (3 tests).

```bash
git add backend/app/api/gate_items.py backend/app/main.py backend/tests/test_api/test_gate_items.py
git commit -m "feat(api): GET /gate-items + POST /gate-items/{id}/resolve"
```

---

## Task 4: `GET /hotspots` — simple "edges in last hour" ranking

**Files:**
- Create: `backend/app/api/hotspots.py`
- Create: `backend/tests/test_api/test_hotspots.py`
- Modify: `backend/app/main.py`

For v0.1 we use the simplest possible "hot" heuristic: count the number of edges incident on each node (in or out) in the last hour. Top N by count are hot. The frontend renders these as glowing nodes. v0.2 can replace with a proper scoring formula.

- [ ] **Step 1: failing test**

```python
# backend/tests/test_api/test_hotspots.py
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.hotspots import build_hotspots_router
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, EdgeRecord, NodeType, ThoughtNode


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bet1 = BetNode(slug="hot", title="Hot bet", vault_path="x.md", owner="cto")
    bet2 = BetNode(slug="cold", title="Cold bet", vault_path="y.md", owner="cto")
    nodes.create(bet1)
    nodes.create(bet2)
    # 5 thoughts pointing to bet1 (hot), 1 thought pointing to bet2 (cold)
    for i in range(5):
        t = ThoughtNode(content=f"t{i}", source="cli")
        nodes.create(t)
        edges.create(EdgeRecord(
            from_id=t.id, from_type=NodeType.THOUGHT,
            to_id=bet1.id, to_type=NodeType.BET,
            edge_type="sparred-against",
        ))
    t = ThoughtNode(content="x", source="cli")
    nodes.create(t)
    edges.create(EdgeRecord(
        from_id=t.id, from_type=NodeType.THOUGHT,
        to_id=bet2.id, to_type=NodeType.BET,
        edge_type="sparred-against",
    ))
    app = FastAPI()
    app.include_router(build_hotspots_router(conn=conn))
    yield {"app": app, "hot": bet1, "cold": bet2}
    conn.close()


def test_hotspots_ranks_by_recent_edge_count(configured_app):
    client = TestClient(configured_app["app"])
    resp = client.get("/hotspots?limit=2")
    body = resp.json()
    assert len(body) <= 2
    # Hot bet should be first
    assert body[0]["id"] == configured_app["hot"].id
    assert body[0]["edge_count"] >= 5
```

- [ ] **Step 2: implementation**

```python
# backend/app/api/hotspots.py
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.db.kuzu import KuzuConnection


def build_hotspots_router(*, conn: KuzuConnection) -> APIRouter:
    router = APIRouter()

    @router.get("/hotspots")
    def hotspots(
        within_hours: int = Query(default=1, ge=1, le=168),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> list[dict]:
        threshold = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        # Count incident edges per node within the time window.
        # Kuzu doesn't yet support GROUP BY in all versions; we collect rows then aggregate in Python.
        rows = conn.query(
            "MATCH (a)-[r:REL]->(b) WHERE r.created_at > $threshold "
            "RETURN a.id AS a_id, b.id AS b_id, label(a) AS a_table, label(b) AS b_table",
            {"threshold": threshold},
        )
        counts: dict[tuple[str, str], int] = {}
        for r in rows:
            counts[(r["a_id"], r["a_table"])] = counts.get((r["a_id"], r["a_table"]), 0) + 1
            counts[(r["b_id"], r["b_table"])] = counts.get((r["b_id"], r["b_table"]), 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
        return [
            {"id": k[0], "type": k[1], "edge_count": v}
            for k, v in ranked
        ]

    return router
```

**Note on Kuzu's `label(n)` function:** Plan 1's retrieval task showed this can vary by Kuzu version. If `label(a)` errors at runtime, fall back to per-table queries (UNION across all 12 tables) — same approach as `app/sparring/retrieval.py`.

- [ ] **Step 3: mount + tests + commit**

Mount: `app.include_router(build_hotspots_router(conn=conn))`.

Run + commit:

```bash
cd backend && uv run pytest tests/test_api/test_hotspots.py -v
git add backend/app/api/hotspots.py backend/app/main.py backend/tests/test_api/test_hotspots.py
git commit -m "feat(api): GET /hotspots ranks nodes by recent edge count"
```

---

## Task 5: `GET /search` — vector + text search

**Files:**
- Create: `backend/app/api/search.py`
- Create: `backend/tests/test_api/test_search.py`
- Modify: `backend/app/main.py`

Frontend search input ships in v0.2, but the endpoint lands here so it's ready. Combines: (1) vector search via `VectorStore.search` if an embedder is configured, (2) plain LIKE search across `Thought.content`, `Bet.title`, etc. as a fallback.

- [ ] **Step 1: failing test (just text search; vector search uses a mocked embedder)**

```python
# backend/tests/test_api/test_search.py
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.search import build_search_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode
from app.db.vector import VectorStore


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    nodes.create(BetNode(slug="auth-pivot", title="Pivot to OAuth",
                         vault_path="x.md", owner="cto"))
    nodes.create(BetNode(slug="ui-redesign", title="Redesign UI",
                         vault_path="y.md", owner="cto"))
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    embedder = AsyncMock()
    embedder.embed.return_value = [1.0, 0.0, 0.0, 0.0]
    embedder.dim = 4

    app = FastAPI()
    app.include_router(build_search_router(conn=conn, vec=vec, embedder=embedder))
    yield app
    vec.close()
    conn.close()


def test_text_search_returns_matching_bet(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/search?q=oauth&mode=text")
    body = resp.json()
    assert any("OAuth" in n.get("summary", "") or n.get("slug") == "auth-pivot"
               for n in body)
```

- [ ] **Step 2: implementation**

```python
# backend/app/api/search.py
from typing import Literal

from fastapi import APIRouter, Query

from app.db.kuzu import KuzuConnection
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider


def build_search_router(
    *, conn: KuzuConnection, vec: VectorStore, embedder: EmbeddingsProvider,
) -> APIRouter:
    router = APIRouter()

    @router.get("/search")
    async def search(
        q: str = Query(..., min_length=1),
        mode: Literal["vector", "text"] = "vector",
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[dict]:
        if mode == "vector":
            embedding = await embedder.embed(q)
            matches = vec.search(embedding, top_k=limit)
            seed_ids = [m["id"] for m in matches]
            results = []
            for table in ["Thought", "Bet", "Decision", "Conflict", "Doc",
                          "GateItem", "CodeChange", "Outcome", "Conversation"]:
                rows = conn.query(
                    f"MATCH (n:{table}) WHERE n.id IN $ids RETURN n.id AS id",
                    {"ids": seed_ids},
                )
                for r in rows:
                    results.append({"id": r["id"], "type": table})
            return results

        # Text mode: LIKE against the content-bearing columns
        like = f"%{q}%"
        text_queries = [
            ("Thought", "content"),
            ("Bet", "title"),
            ("Bet", "slug"),
            ("Decision", "content"),
            ("Doc", "title"),
            ("Conflict", "summary"),
            ("Outcome", "summary"),
        ]
        results = []
        for table, col in text_queries:
            rows = conn.query(
                f"MATCH (n:{table}) WHERE n.{col} CONTAINS $needle "
                f"RETURN n.id AS id, n.{col} AS summary LIMIT $limit",
                {"needle": q, "limit": limit},
            )
            for r in rows:
                results.append({"id": r["id"], "type": table,
                                "summary": r.get("summary", "")})
        return results[:limit]

    return router
```

- [ ] **Step 3: mount + tests + commit**

Mount: `app.include_router(build_search_router(conn=conn, vec=vec, embedder=embedder))`.

```bash
cd backend && uv run pytest tests/test_api/test_search.py -v
git add backend/app/api/search.py backend/app/main.py backend/tests/test_api/test_search.py
git commit -m "feat(api): GET /search supports text and vector modes"
```

---

# Section B — Frontend foundation (5 tasks)

## Task 6: frontend project scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles/globals.css`
- Modify: `.gitignore` (add `frontend/node_modules`, `frontend/dist`)

- [ ] **Step 1: package.json**

```json
{
  "name": "gigabrain-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx --max-warnings 0",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "cytoscape": "^3.30.0"
  },
  "devDependencies": {
    "@types/cytoscape": "^3.21.5",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@typescript-eslint/eslint-plugin": "^7.13.0",
    "@typescript-eslint/parser": "^7.13.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "eslint": "^8.57.0",
    "eslint-plugin-react": "^7.34.3",
    "eslint-plugin-react-hooks": "^4.6.2",
    "eslint-plugin-react-refresh": "^0.4.7",
    "jsdom": "^24.1.0",
    "postcss": "^8.4.39",
    "tailwindcss": "^3.4.4",
    "typescript": "^5.5.2",
    "vite": "^5.3.1",
    "vitest": "^1.6.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6"
  }
}
```

- [ ] **Step 2: tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    proxy: {
      "/capture": "http://localhost:8000",
      "/graph": "http://localhost:8000",
      "/nodes": "http://localhost:8000",
      "/gate-items": "http://localhost:8000",
      "/hotspots": "http://localhost:8000",
      "/search": "http://localhost:8000",
      "/agents": "http://localhost:8000",
      "/stream": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
```

- [ ] **Step 5: tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Node-type palette matching spec §4
        bet: "#a855f7",
        gate: "#fbbf24",
        conflict: "#f87171",
        thought: "#4ade80",
        firing: "#ec4899",
        codechange: "#60a5fa",
        doc: "#818cf8",
        hotspot: "#f97316",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 6: postcss.config.js**

```javascript
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 7: index.html**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>GigaBrain</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: src/main.tsx + src/App.tsx + src/styles/globals.css**

```typescript
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

```typescript
// frontend/src/App.tsx
export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <h1 className="p-4 text-xl font-bold">GigaBrain</h1>
      <p className="px-4 text-sm text-gray-400">Brain view — placeholder</p>
    </div>
  );
}
```

```css
/* frontend/src/styles/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root {
  height: 100%;
  margin: 0;
  font-family: ui-sans-serif, system-ui, sans-serif;
}
```

- [ ] **Step 9: tests/setup.ts**

```typescript
// frontend/tests/setup.ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 10: gitignore + install + smoke + commit**

Append to `.gitignore`:

```
frontend/node_modules/
frontend/dist/
frontend/.vite/
```

Install + smoke:

```bash
cd frontend
npm install
npm run build
```

Expected: build succeeds; `frontend/dist/` exists.

```bash
git add frontend/package.json frontend/tsconfig.json frontend/tsconfig.node.json \
        frontend/vite.config.ts frontend/tailwind.config.js frontend/postcss.config.js \
        frontend/index.html frontend/src/ frontend/tests/setup.ts .gitignore
# DO NOT add frontend/package-lock.json yet — that comes after npm i
git add frontend/package-lock.json
git commit -m "feat(frontend): scaffold Vite + React + TS + Tailwind"
```

---

## Task 7: API client + TypeScript types

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/tests/api/client.test.ts`

- [ ] **Step 1: types**

```typescript
// frontend/src/api/types.ts
export type NodeType =
  | "Thought" | "Bet" | "Task" | "Decision" | "Conflict" | "Outcome"
  | "AgentFiring" | "CodeChange" | "Conversation" | "Doc" | "GateItem";

export interface NodeRow {
  id: string;
  type: NodeType;
  created_at: string;
}

export interface EdgeRow {
  from_id: string;
  to_id: string;
  edge_type: string;
  created_at: string;
}

export interface NodeDetail {
  id: string;
  type: NodeType;
  props: Record<string, unknown>;
  outgoing_edges: { edge_type: string; to_id: string; confidence: number }[];
  incoming_edges: { edge_type: string; from_id: string; confidence: number }[];
}

export interface GateItem {
  id: string;
  prompt: string;
  urgency: "urgent" | "high" | "medium" | "novel" | "low" | string;
  created_at: string;
}

export interface HotSpot {
  id: string;
  type: NodeType;
  edge_count: number;
}

export type GateDecision = "approved" | "vetoed" | "resteered";
```

- [ ] **Step 2: client + test (TDD)**

```typescript
// frontend/tests/api/client.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";
import { api } from "@/api/client";

describe("api client", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("getGraph fetches /graph and returns parsed body", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ nodes: [{ id: "t_1", type: "Thought", created_at: "" }], edges: [] }),
    });
    const res = await api.getGraph();
    expect(fetch).toHaveBeenCalledWith("/graph", expect.anything());
    expect(res.nodes).toHaveLength(1);
  });

  it("capture posts to /capture with body", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true, json: async () => ({ node_id: "t_x", status: "sparring" }),
    });
    await api.capture({ content: "hi", source: "web" });
    const call = (fetch as any).mock.calls[0];
    expect(call[0]).toBe("/capture");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toMatchObject({ content: "hi", source: "web" });
  });

  it("throws on non-ok response", async () => {
    (fetch as any).mockResolvedValueOnce({ ok: false, status: 500 });
    await expect(api.getGraph()).rejects.toThrow();
  });
});
```

```typescript
// frontend/src/api/client.ts
import type {
  NodeRow, EdgeRow, NodeDetail, GateItem, HotSpot, GateDecision, NodeType,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    throw new Error(`API ${path} returned ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async getGraph(types?: NodeType[], limit = 2000):
      Promise<{ nodes: NodeRow[]; edges: EdgeRow[] }> {
    const params = new URLSearchParams();
    if (types?.length) params.set("types", types.join(","));
    params.set("limit", String(limit));
    return request(`/graph?${params}`);
  },

  async getNode(table: NodeType, id: string): Promise<NodeDetail> {
    return request(`/nodes/${table}/${encodeURIComponent(id)}`);
  },

  async getGateItems(): Promise<GateItem[]> {
    return request("/gate-items");
  },

  async resolveGateItem(
    id: string,
    decision: GateDecision,
    reasoning = "",
  ): Promise<{ id: string; decision: string; resolved_at: string }> {
    return request(`/gate-items/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ decision, reasoning }),
    });
  },

  async getHotspots(limit = 10, withinHours = 1): Promise<HotSpot[]> {
    const params = new URLSearchParams({ limit: String(limit), within_hours: String(withinHours) });
    return request(`/hotspots?${params}`);
  },

  async capture(input: { content: string; source: string; metadata?: Record<string, unknown> }):
      Promise<{ node_id: string; status: string }> {
    return request("/capture", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
};
```

- [ ] **Step 3: run + commit**

```bash
cd frontend && npm run test
```
Expected: 3 tests pass.

```bash
git add frontend/src/api/ frontend/tests/api/
git commit -m "feat(frontend): typed API client with vitest coverage"
```

---

## Task 8: SSE event stream hook

**Files:**
- Create: `frontend/src/api/stream.ts`
- Create: `frontend/tests/api/stream.test.ts`

- [ ] **Step 1: failing test**

```typescript
// frontend/tests/api/stream.test.ts
import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useEventStream } from "@/api/stream";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
  }
}

describe("useEventStream", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    (globalThis as any).EventSource = MockEventSource;
  });

  it("opens an EventSource on mount and closes on unmount", () => {
    const { unmount } = renderHook(() => useEventStream("/stream", () => {}));
    expect(MockEventSource.instances).toHaveLength(1);
    unmount();
    expect(MockEventSource.instances[0].closed).toBe(true);
  });

  it("delivers parsed JSON payloads to the callback", () => {
    const handler = vi.fn();
    renderHook(() => useEventStream("/stream", handler));
    const es = MockEventSource.instances[0];
    act(() => {
      es.onmessage?.(new MessageEvent("message", { data: '{"event":"graph.changed","node_id":"t_1"}' }));
    });
    expect(handler).toHaveBeenCalledWith({ event: "graph.changed", node_id: "t_1" });
  });
});
```

- [ ] **Step 2: implementation**

```typescript
// frontend/src/api/stream.ts
import { useEffect } from "react";

export type StreamEvent =
  | { event: "graph.changed"; change_type: string; node_id?: string; edge_id?: string }
  | { event: "gate.created"; gate_item_id: string; thought_id: string; urgency: string }
  | { event: "fire.neuron"; thought_id: string; agent_role: string; task_summary: string };

export function useEventStream(url: string, onEvent: (e: StreamEvent) => void) {
  useEffect(() => {
    const es = new EventSource(url);
    es.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data) as StreamEvent;
        onEvent(parsed);
      } catch {
        // Ignore non-JSON keepalive comments
      }
    };
    es.onerror = () => {
      // Browser will auto-reconnect; we don't need to do anything special
    };
    return () => es.close();
  }, [url, onEvent]);
}
```

- [ ] **Step 3: tests + commit**

```bash
cd frontend && npm run test
git add frontend/src/api/stream.ts frontend/tests/api/stream.test.ts
git commit -m "feat(frontend): useEventStream hook with vitest coverage"
```

---

## Task 9: GraphProvider — central state synced from REST + SSE

**Files:**
- Create: `frontend/src/state/GraphProvider.tsx`
- Create: `frontend/src/state/useGraph.ts`
- Create: `frontend/tests/state/GraphProvider.test.tsx`

The provider:
1. Loads initial graph via `api.getGraph()` on mount
2. Loads hotspots + gate items
3. Wires `useEventStream` to apply SSE updates incrementally
4. Exposes `nodes`, `edges`, `gateItems`, `hotspots`, plus mutation helpers

- [ ] **Step 1: failing test**

```typescript
// frontend/tests/state/GraphProvider.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { GraphProvider } from "@/state/GraphProvider";
import { useGraph } from "@/state/useGraph";

vi.mock("@/api/client", () => ({
  api: {
    getGraph: vi.fn(async () => ({
      nodes: [{ id: "b_1", type: "Bet", created_at: "" }],
      edges: [],
    })),
    getGateItems: vi.fn(async () => []),
    getHotspots: vi.fn(async () => []),
  },
}));

vi.mock("@/api/stream", () => ({ useEventStream: () => {} }));

function Probe() {
  const { nodes } = useGraph();
  return <div data-testid="count">{nodes.length}</div>;
}

describe("GraphProvider", () => {
  it("loads initial graph and exposes nodes via useGraph", async () => {
    render(
      <GraphProvider>
        <Probe />
      </GraphProvider>
    );
    await waitFor(() =>
      expect(screen.getByTestId("count").textContent).toBe("1")
    );
  });
});
```

- [ ] **Step 2: implementation**

```typescript
// frontend/src/state/GraphProvider.tsx
import {
  createContext, ReactNode, useCallback, useEffect, useState,
} from "react";
import { api } from "@/api/client";
import { useEventStream, StreamEvent } from "@/api/stream";
import type { NodeRow, EdgeRow, GateItem, HotSpot } from "@/api/types";

interface GraphState {
  nodes: NodeRow[];
  edges: EdgeRow[];
  gateItems: GateItem[];
  hotspots: HotSpot[];
  refresh: () => Promise<void>;
}

export const GraphContext = createContext<GraphState | null>(null);

export function GraphProvider({ children }: { children: ReactNode }) {
  const [nodes, setNodes] = useState<NodeRow[]>([]);
  const [edges, setEdges] = useState<EdgeRow[]>([]);
  const [gateItems, setGateItems] = useState<GateItem[]>([]);
  const [hotspots, setHotspots] = useState<HotSpot[]>([]);

  const refresh = useCallback(async () => {
    const [g, gi, hs] = await Promise.all([
      api.getGraph(), api.getGateItems(), api.getHotspots(),
    ]);
    setNodes(g.nodes);
    setEdges(g.edges);
    setGateItems(gi);
    setHotspots(hs);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const onEvent = useCallback((event: StreamEvent) => {
    if (event.event === "graph.changed") {
      // Incremental: re-fetch the affected slice. Cheap since we only refresh on
      // events; for v0.1 just re-pull the whole graph (graphs are small).
      void refresh();
    } else if (event.event === "gate.created") {
      void api.getGateItems().then(setGateItems);
    }
  }, [refresh]);
  useEventStream("/stream", onEvent);

  return (
    <GraphContext.Provider value={{ nodes, edges, gateItems, hotspots, refresh }}>
      {children}
    </GraphContext.Provider>
  );
}
```

```typescript
// frontend/src/state/useGraph.ts
import { useContext } from "react";
import { GraphContext } from "./GraphProvider";

export function useGraph() {
  const ctx = useContext(GraphContext);
  if (!ctx) throw new Error("useGraph must be used inside <GraphProvider>");
  return ctx;
}
```

- [ ] **Step 3: tests + commit**

```bash
cd frontend && npm run test
git add frontend/src/state/ frontend/tests/state/
git commit -m "feat(frontend): GraphProvider with REST init and SSE-driven updates"
```

---

## Task 10: layout shell — wire BrainView into App.tsx

**Files:**
- Create: `frontend/src/views/BrainView.tsx`
- Create: `frontend/src/views/TopBar.tsx`
- Modify: `frontend/src/App.tsx`

A simple grid layout: TopBar (with live counts), main canvas area (placeholder until Task 11), right side panel (placeholder until Task 13), bottom CaptureBar (Task 14).

- [ ] **Step 1: TopBar**

```typescript
// frontend/src/views/TopBar.tsx
import { useGraph } from "@/state/useGraph";

export default function TopBar() {
  const { gateItems, hotspots } = useGraph();
  return (
    <div className="flex items-center justify-between border-b border-gray-800 bg-gray-900 px-4 py-2">
      <div className="text-sm font-bold text-purple-300">🧠 GigaBrain</div>
      <div className="flex gap-2 text-xs">
        <span className="rounded-full border border-yellow-400 bg-yellow-900/30 px-2 py-0.5 text-yellow-300">
          ⚡ {gateItems.length} gate items
        </span>
        <span className="rounded-full border border-orange-400 bg-orange-900/30 px-2 py-0.5 text-orange-300">
          🔥 {hotspots.length} hot spots
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: BrainView**

```typescript
// frontend/src/views/BrainView.tsx
import TopBar from "./TopBar";

export default function BrainView() {
  return (
    <div className="flex h-screen flex-col bg-gray-950">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 bg-gray-950 p-4 text-gray-500">
          (graph canvas placeholder — Task 11)
        </main>
        <aside className="w-80 border-l border-gray-800 bg-gray-900 p-4 text-gray-500">
          (node detail placeholder — Task 13)
        </aside>
      </div>
      <div className="border-t border-gray-800 bg-gray-900 p-2 text-gray-500">
        (capture bar placeholder — Task 14)
      </div>
    </div>
  );
}
```

- [ ] **Step 3: App.tsx**

```typescript
// frontend/src/App.tsx
import BrainView from "./views/BrainView";
import { GraphProvider } from "./state/GraphProvider";

export default function App() {
  return (
    <GraphProvider>
      <BrainView />
    </GraphProvider>
  );
}
```

- [ ] **Step 4: smoke + commit**

```bash
cd frontend && npm run build
git add frontend/src/App.tsx frontend/src/views/BrainView.tsx frontend/src/views/TopBar.tsx
git commit -m "feat(frontend): layout shell with TopBar showing live counts"
```

---

# Section C — Frontend graph view (4 tasks)

## Task 11: GraphCanvas — Cytoscape integration

**Files:**
- Create: `frontend/src/utils/nodeColors.ts`
- Create: `frontend/src/views/GraphCanvas.tsx`
- Create: `frontend/tests/views/GraphCanvas.test.tsx`
- Modify: `frontend/src/views/BrainView.tsx`

Renders nodes from `useGraph()` as a force-directed Cytoscape graph. Node fill uses the type-color palette from spec §4.

- [ ] **Step 1: nodeColors util**

```typescript
// frontend/src/utils/nodeColors.ts
import type { NodeType } from "@/api/types";

export const NODE_COLORS: Record<NodeType, string> = {
  Thought: "#4ade80",
  Bet: "#a855f7",
  Task: "#94a3b8",
  Decision: "#22c55e",
  Conflict: "#f87171",
  Outcome: "#34d399",
  AgentFiring: "#ec4899",
  CodeChange: "#60a5fa",
  Conversation: "#fbbf24",
  Doc: "#818cf8",
  GateItem: "#fbbf24",
};

export function colorForType(type: NodeType): string {
  return NODE_COLORS[type] ?? "#9ca3af";
}
```

- [ ] **Step 2: failing test (renders without crashing, registers nodes)**

```typescript
// frontend/tests/views/GraphCanvas.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import GraphCanvas from "@/views/GraphCanvas";
import { GraphContext } from "@/state/GraphProvider";

const fakeContext = {
  nodes: [
    { id: "t_1", type: "Thought" as const, created_at: "" },
    { id: "b_1", type: "Bet" as const, created_at: "" },
  ],
  edges: [{ from_id: "t_1", to_id: "b_1", edge_type: "sparred-against", created_at: "" }],
  gateItems: [],
  hotspots: [],
  refresh: vi.fn(),
};

describe("GraphCanvas", () => {
  it("renders without crashing given nodes and edges", () => {
    const { container } = render(
      <GraphContext.Provider value={fakeContext}>
        <GraphCanvas onSelectNode={() => {}} />
      </GraphContext.Provider>
    );
    expect(container.querySelector("[data-testid='cy-host']")).toBeTruthy();
  });
});
```

- [ ] **Step 3: implementation**

```typescript
// frontend/src/views/GraphCanvas.tsx
import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import { useGraph } from "@/state/useGraph";
import { colorForType } from "@/utils/nodeColors";
import type { NodeType } from "@/api/types";

interface Props {
  onSelectNode: (table: NodeType, id: string) => void;
}

export default function GraphCanvas({ onSelectNode }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const { nodes, edges, hotspots, gateItems } = useGraph();

  // Initialize once
  useEffect(() => {
    if (!hostRef.current) return;
    cyRef.current = cytoscape({
      container: hostRef.current,
      elements: [],
      layout: { name: "cose" },
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#e5e7eb",
            "font-size": 9,
            width: 20,
            height: 20,
          },
        },
        {
          selector: "node[?hot]",
          style: {
            "border-color": "#f97316",
            "border-width": 4,
            "shadow-color": "#f97316",
            "shadow-blur": 18,
            "shadow-opacity": 0.7,
          },
        },
        {
          selector: "node[?gate]",
          style: {
            "border-color": "#fbbf24",
            "border-width": 3,
          },
        },
        {
          selector: "edge",
          style: {
            "line-color": "#4b5563",
            "target-arrow-color": "#4b5563",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            width: 1,
          },
        },
      ],
    });

    cyRef.current.on("tap", "node", (evt) => {
      const data = evt.target.data();
      onSelectNode(data.nodeType as NodeType, data.id);
    });

    return () => { cyRef.current?.destroy(); cyRef.current = null; };
  }, [onSelectNode]);

  // Sync data when graph state changes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const hotIds = new Set(hotspots.map(h => h.id));
    const gateIds = new Set(gateItems.map(g => g.id));
    const cyElements = [
      ...nodes.map(n => ({
        data: {
          id: n.id, label: `${n.type[0]} ${n.id.slice(-4)}`,
          color: colorForType(n.type),
          nodeType: n.type,
          hot: hotIds.has(n.id) ? 1 : 0,
          gate: gateIds.has(n.id) ? 1 : 0,
        },
      })),
      ...edges.map(e => ({
        data: {
          id: `${e.from_id}->${e.to_id}->${e.edge_type}`,
          source: e.from_id, target: e.to_id,
        },
      })),
    ];
    cy.json({ elements: cyElements });
    cy.layout({ name: "cose", animate: false }).run();
  }, [nodes, edges, hotspots, gateItems]);

  return (
    <div
      ref={hostRef}
      data-testid="cy-host"
      className="h-full w-full"
    />
  );
}
```

- [ ] **Step 4: wire in BrainView**

Replace the `<main>` placeholder:

```typescript
// frontend/src/views/BrainView.tsx
import { useState } from "react";
import TopBar from "./TopBar";
import GraphCanvas from "./GraphCanvas";
import type { NodeType } from "@/api/types";

export default function BrainView() {
  const [selected, setSelected] = useState<{ table: NodeType; id: string } | null>(null);
  return (
    <div className="flex h-screen flex-col bg-gray-950">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1">
          <GraphCanvas onSelectNode={(table, id) => setSelected({ table, id })} />
        </main>
        <aside className="w-80 border-l border-gray-800 bg-gray-900 p-4 text-gray-300 text-xs">
          {selected ? `${selected.table} ${selected.id}` : "(select a node)"}
        </aside>
      </div>
      <div className="border-t border-gray-800 bg-gray-900 p-2 text-gray-500">
        (capture bar placeholder — Task 14)
      </div>
    </div>
  );
}
```

- [ ] **Step 5: tests + smoke + commit**

```bash
cd frontend && npm run test && npm run build
git add frontend/src/utils/ frontend/src/views/GraphCanvas.tsx \
        frontend/src/views/BrainView.tsx frontend/tests/views/GraphCanvas.test.tsx
git commit -m "feat(frontend): GraphCanvas renders Cytoscape graph with hot/gate styling"
```

---

## Task 12: NodeDetail panel — fetches `/nodes/{table}/{id}` on selection

**Files:**
- Create: `frontend/src/views/NodeDetail.tsx`
- Modify: `frontend/src/views/BrainView.tsx`

Right side panel that fetches the selected node's full props + edges. Shows "(select a node)" when nothing is selected.

- [ ] **Step 1: implementation**

```typescript
// frontend/src/views/NodeDetail.tsx
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { NodeDetail as NodeDetailT, NodeType } from "@/api/types";

interface Props {
  table: NodeType | null;
  nodeId: string | null;
}

export default function NodeDetail({ table, nodeId }: Props) {
  const [data, setData] = useState<NodeDetailT | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!table || !nodeId) {
      setData(null);
      return;
    }
    setError(null);
    api.getNode(table, nodeId)
      .then(setData)
      .catch(e => setError(String(e)));
  }, [table, nodeId]);

  if (!table || !nodeId) return <div className="text-xs text-gray-500">(select a node)</div>;
  if (error) return <div className="text-xs text-red-400">{error}</div>;
  if (!data) return <div className="text-xs text-gray-500">loading…</div>;

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-300">{data.type}</span>
        <span className="text-gray-500">{data.id}</span>
      </div>
      <pre className="whitespace-pre-wrap break-words rounded bg-gray-950 p-2 text-gray-300">
        {JSON.stringify(data.props, null, 2)}
      </pre>
      {data.outgoing_edges.length > 0 && (
        <div>
          <div className="mb-1 text-gray-400 uppercase">→ outgoing</div>
          {data.outgoing_edges.map((e, i) => (
            <div key={i} className="font-mono text-gray-300">
              [{e.edge_type}] → {e.to_id}
            </div>
          ))}
        </div>
      )}
      {data.incoming_edges.length > 0 && (
        <div>
          <div className="mb-1 text-gray-400 uppercase">← incoming</div>
          {data.incoming_edges.map((e, i) => (
            <div key={i} className="font-mono text-gray-300">
              {e.from_id} → [{e.edge_type}]
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: BrainView wiring**

Replace the placeholder `<aside>` content:

```typescript
<aside className="w-80 border-l border-gray-800 bg-gray-900 p-4">
  <NodeDetail
    table={selected?.table ?? null}
    nodeId={selected?.id ?? null}
  />
</aside>
```

- [ ] **Step 3: smoke + commit**

```bash
cd frontend && npm run build
git add frontend/src/views/NodeDetail.tsx frontend/src/views/BrainView.tsx
git commit -m "feat(frontend): NodeDetail panel fetches node props + edges on selection"
```

---

## Task 13: hot spot pulse animation on graph

**Files:**
- Modify: `frontend/src/views/GraphCanvas.tsx` (add CSS animation for hot nodes)
- Modify: `frontend/src/styles/globals.css` (declare keyframes)

Hot nodes already get an orange border from Task 11. Add a CSS-driven pulse to make them visually obvious.

- [ ] **Step 1: keyframes**

In `frontend/src/styles/globals.css`, append:

```css
@keyframes hot-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.cy-hot-overlay {
  animation: hot-pulse 1.5s ease-in-out infinite;
}
```

- [ ] **Step 2: in GraphCanvas, animate nodes via Cytoscape style updates**

Cytoscape doesn't directly support CSS classes like the DOM, so use periodic `style` updates:

In `GraphCanvas.tsx`, after the cy initialization, add:

```typescript
useEffect(() => {
  const cy = cyRef.current;
  if (!cy) return;
  let phase = 0;
  const id = window.setInterval(() => {
    phase = (phase + 1) % 60;
    const factor = 0.7 + 0.3 * Math.abs(Math.sin((phase / 60) * Math.PI * 2));
    cy.nodes("[?hot]").style({ "shadow-opacity": factor });
  }, 50);
  return () => window.clearInterval(id);
}, []);
```

- [ ] **Step 3: smoke + commit**

```bash
cd frontend && npm run build
git add frontend/src/views/GraphCanvas.tsx frontend/src/styles/globals.css
git commit -m "feat(frontend): pulse animation on hot-spot nodes"
```

---

## Task 14: gate item highlighting + click-through to NodeDetail

This is partly already done — Task 11 added a yellow border to gate items, and Task 12 lets you click any node to see its detail. The gap: we need a way to *also* click a gate item from the gate item list (Task 16 below) and have the canvas focus on it.

For Task 14, add a `selectNode` capability via `useGraph` so any panel can request canvas selection.

**Files:**
- Modify: `frontend/src/state/GraphProvider.tsx` (add `selectionRequest` state + `requestSelect`)
- Modify: `frontend/src/state/useGraph.ts`
- Modify: `frontend/src/views/GraphCanvas.tsx` (react to selectionRequest)

- [ ] **Step 1: extend GraphProvider**

Inside `GraphProvider`, add:

```typescript
const [selectionRequest, setSelectionRequest] = useState<{ table: NodeType; id: string } | null>(null);
// ... in the Provider value:
return (
  <GraphContext.Provider value={{
    nodes, edges, gateItems, hotspots, refresh,
    selectionRequest,
    requestSelect: (table: NodeType, id: string) => setSelectionRequest({ table, id }),
    clearSelectionRequest: () => setSelectionRequest(null),
  }}>
```

Update the `GraphState` interface accordingly.

- [ ] **Step 2: GraphCanvas reacts to selectionRequest**

In `GraphCanvas.tsx`, after the data-sync `useEffect`, add:

```typescript
const { selectionRequest, clearSelectionRequest } = useGraph();
useEffect(() => {
  const cy = cyRef.current;
  if (!cy || !selectionRequest) return;
  const node = cy.getElementById(selectionRequest.id);
  if (node) {
    cy.center(node);
    cy.animate({ fit: { eles: node, padding: 60 } }, { duration: 300 });
    onSelectNode(selectionRequest.table, selectionRequest.id);
  }
  clearSelectionRequest();
}, [selectionRequest, clearSelectionRequest, onSelectNode]);
```

- [ ] **Step 3: smoke + commit**

```bash
cd frontend && npm run build
git add frontend/src/state/ frontend/src/views/GraphCanvas.tsx
git commit -m "feat(frontend): cross-component node selection via GraphProvider"
```

---

# Section D — Frontend interactions (3 tasks)

## Task 15: CaptureBar — POST /capture and let SSE refresh the graph

**Files:**
- Create: `frontend/src/views/CaptureBar.tsx`
- Create: `frontend/tests/views/CaptureBar.test.tsx`
- Modify: `frontend/src/views/BrainView.tsx`

- [ ] **Step 1: failing test**

```typescript
// frontend/tests/views/CaptureBar.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import CaptureBar from "@/views/CaptureBar";
import { api } from "@/api/client";

vi.mock("@/api/client", () => ({
  api: { capture: vi.fn() },
}));

describe("CaptureBar", () => {
  beforeEach(() => { vi.mocked(api.capture).mockReset(); });

  it("submits content on Enter", async () => {
    vi.mocked(api.capture).mockResolvedValueOnce({ node_id: "t_1", status: "sparring" });
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/dump a thought/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "ship oauth" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(api.capture).toHaveBeenCalledWith({ content: "ship oauth", source: "web" });
  });

  it("clears input on success", async () => {
    vi.mocked(api.capture).mockResolvedValueOnce({ node_id: "t_1", status: "sparring" });
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/dump a thought/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "x" } });
    fireEvent.keyDown(input, { key: "Enter" });
    // Wait microtask for promise resolution
    await Promise.resolve();
    await Promise.resolve();
    expect(input.value).toBe("");
  });
});
```

- [ ] **Step 2: implementation**

```typescript
// frontend/src/views/CaptureBar.tsx
import { useState } from "react";
import { api } from "@/api/client";

export default function CaptureBar() {
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const trimmed = content.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await api.capture({ content: trimmed, source: "web" });
      setContent("");
    } catch (e) {
      // Surface to console — UI toasts can land in v0.2
      console.error(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2 border-t border-gray-800 bg-gray-900 p-2">
      <span className="text-green-400">💭</span>
      <input
        className="flex-1 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 placeholder-gray-500 focus:border-purple-400 focus:outline-none"
        placeholder="dump a thought..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
        disabled={busy}
      />
      <button
        onClick={() => void submit()}
        disabled={busy}
        className="rounded bg-purple-500 px-3 py-1 text-sm text-white disabled:opacity-50"
      >
        spar →
      </button>
    </div>
  );
}
```

- [ ] **Step 3: wire in BrainView**

Replace the bottom placeholder:

```typescript
import CaptureBar from "./CaptureBar";
// ...
<CaptureBar />
```

- [ ] **Step 4: tests + commit**

```bash
cd frontend && npm run test
git add frontend/src/views/CaptureBar.tsx frontend/src/views/BrainView.tsx \
        frontend/tests/views/CaptureBar.test.tsx
git commit -m "feat(frontend): CaptureBar posts to /capture and clears on success"
```

---

## Task 16: GateItemList + GateItemResolveModal

**Files:**
- Create: `frontend/src/views/GateItemList.tsx`
- Create: `frontend/src/components/GateItemResolveModal.tsx`
- Create: `frontend/tests/views/GateItemList.test.tsx`
- Modify: `frontend/src/views/BrainView.tsx`

The list lives in the right panel above NodeDetail. Each item has Approve / Veto / Resteer / Zoom buttons. Resteer opens a modal asking for an alternative + reasoning.

- [ ] **Step 1: GateItemResolveModal**

```typescript
// frontend/src/components/GateItemResolveModal.tsx
import { useState } from "react";
import type { GateDecision } from "@/api/types";

interface Props {
  decision: GateDecision;
  onSubmit: (reasoning: string) => Promise<void>;
  onClose: () => void;
}

export default function GateItemResolveModal({ decision, onSubmit, onClose }: Props) {
  const [reasoning, setReasoning] = useState("");
  const [submitting, setSubmitting] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-96 rounded border border-gray-700 bg-gray-900 p-4">
        <h2 className="mb-2 text-sm font-semibold text-gray-200">
          {decision.toUpperCase()} — reasoning
        </h2>
        <textarea
          className="h-24 w-full rounded border border-gray-700 bg-gray-800 p-2 text-sm text-gray-100"
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value)}
          placeholder="why?"
        />
        <div className="mt-3 flex justify-end gap-2 text-sm">
          <button onClick={onClose} className="rounded bg-gray-700 px-3 py-1 text-gray-100">
            cancel
          </button>
          <button
            onClick={async () => {
              setSubmitting(true);
              try { await onSubmit(reasoning); onClose(); }
              finally { setSubmitting(false); }
            }}
            disabled={submitting}
            className="rounded bg-purple-500 px-3 py-1 text-white disabled:opacity-50"
          >
            confirm
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: GateItemList**

```typescript
// frontend/src/views/GateItemList.tsx
import { useState } from "react";
import { api } from "@/api/client";
import { useGraph } from "@/state/useGraph";
import GateItemResolveModal from "@/components/GateItemResolveModal";
import type { GateDecision } from "@/api/types";

export default function GateItemList() {
  const { gateItems, refresh } = useGraph();
  const [pendingDecision, setPendingDecision] = useState<{ id: string; decision: GateDecision } | null>(null);

  async function quickResolve(id: string, decision: GateDecision) {
    await api.resolveGateItem(id, decision, "");
    await refresh();
  }

  return (
    <div className="space-y-2">
      <div className="text-xs uppercase text-gray-400">⚡ gate items ({gateItems.length})</div>
      {gateItems.length === 0 && (
        <div className="text-xs text-gray-500">(none pending)</div>
      )}
      {gateItems.map(g => (
        <div key={g.id} className="rounded border border-yellow-500/30 bg-yellow-900/10 p-2">
          <div className="text-xs text-gray-400">{g.urgency}</div>
          <div className="mb-2 text-sm text-gray-100">{g.prompt}</div>
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => quickResolve(g.id, "approved")}
              className="rounded border border-green-500 px-2 py-0.5 text-green-400"
            >approve</button>
            <button
              onClick={() => quickResolve(g.id, "vetoed")}
              className="rounded border border-red-500 px-2 py-0.5 text-red-400"
            >veto</button>
            <button
              onClick={() => setPendingDecision({ id: g.id, decision: "resteered" })}
              className="rounded border border-gray-500 px-2 py-0.5 text-gray-300"
            >resteer</button>
          </div>
        </div>
      ))}
      {pendingDecision && (
        <GateItemResolveModal
          decision={pendingDecision.decision}
          onClose={() => setPendingDecision(null)}
          onSubmit={async (reasoning) => {
            await api.resolveGateItem(pendingDecision.id, pendingDecision.decision, reasoning);
            await refresh();
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: failing test**

```typescript
// frontend/tests/views/GateItemList.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GateItemList from "@/views/GateItemList";
import { GraphContext } from "@/state/GraphProvider";
import { api } from "@/api/client";

vi.mock("@/api/client", () => ({
  api: { resolveGateItem: vi.fn().mockResolvedValue({}) },
}));

const ctx = {
  nodes: [], edges: [], hotspots: [],
  gateItems: [{ id: "g_1", prompt: "ship preview?", urgency: "high", created_at: "" }],
  refresh: vi.fn().mockResolvedValue(undefined),
  selectionRequest: null,
  requestSelect: vi.fn(),
  clearSelectionRequest: vi.fn(),
};

describe("GateItemList", () => {
  it("calls resolveGateItem on Approve click", async () => {
    render(
      <GraphContext.Provider value={ctx as any}>
        <GateItemList />
      </GraphContext.Provider>
    );
    fireEvent.click(screen.getByText("approve"));
    expect(api.resolveGateItem).toHaveBeenCalledWith("g_1", "approved", "");
  });
});
```

- [ ] **Step 4: wire in BrainView**

Update the right `<aside>` to stack GateItemList above NodeDetail:

```typescript
<aside className="flex w-80 flex-col gap-4 border-l border-gray-800 bg-gray-900 p-4 overflow-y-auto">
  <GateItemList />
  <hr className="border-gray-800" />
  <NodeDetail
    table={selected?.table ?? null}
    nodeId={selected?.id ?? null}
  />
</aside>
```

- [ ] **Step 5: tests + commit**

```bash
cd frontend && npm run test
git add frontend/src/components/GateItemResolveModal.tsx frontend/src/views/GateItemList.tsx \
        frontend/src/views/BrainView.tsx frontend/tests/views/GateItemList.test.tsx
git commit -m "feat(frontend): GateItemList with quick approve/veto and resteer modal"
```

---

## Task 17: live updates — verify SSE actually animates new nodes in

This task is mostly verification that the existing wiring works end-to-end. Add a small enhancement: when a `graph.changed` event arrives, briefly highlight the new node.

**Files:**
- Modify: `frontend/src/views/GraphCanvas.tsx` (track new node ids, apply temporary glow)

- [ ] **Step 1: track newly-arrived node ids**

```typescript
const [newIds, setNewIds] = useState<Set<string>>(new Set());

// In the data-sync useEffect, capture which ids are new since last render
const prevIdsRef = useRef<Set<string>>(new Set());
useEffect(() => {
  const currentIds = new Set(nodes.map(n => n.id));
  const additions = nodes.filter(n => !prevIdsRef.current.has(n.id)).map(n => n.id);
  if (additions.length > 0) {
    setNewIds(s => new Set([...s, ...additions]));
    window.setTimeout(() => {
      setNewIds(s => {
        const next = new Set(s);
        for (const id of additions) next.delete(id);
        return next;
      });
    }, 2000);
  }
  prevIdsRef.current = currentIds;
}, [nodes]);
```

Update the cyElements builder to set `data.new` from this set, and add a Cytoscape style for `[?new]`:

```typescript
{
  selector: "node[?new]",
  style: {
    "border-color": "#a855f7",
    "border-width": 6,
    "shadow-color": "#a855f7",
    "shadow-blur": 24,
    "shadow-opacity": 0.9,
  },
},
```

- [ ] **Step 2: smoke + commit**

```bash
cd frontend && npm run build
git add frontend/src/views/GraphCanvas.tsx
git commit -m "feat(frontend): briefly glow newly-arrived nodes from SSE updates"
```

---

# Section E — Integration (2 tasks)

## Task 18: serve frontend dist from FastAPI

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/pyproject.toml` (no new dep — FastAPI's `StaticFiles` is enough)

In production, FastAPI serves the built frontend at `/`. The frontend's API calls hit relative paths like `/capture`, `/graph`, etc. — so they hit the same FastAPI instance.

- [ ] **Step 1: mount StaticFiles**

In `backend/app/main.py`, add at the bottom of `lifespan` (after all `app.include_router(...)` calls):

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path

frontend_dist = _Path(__file__).parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
```

The `html=True` flag makes FastAPI serve `index.html` for any unknown path (so React Router would work in v0.2 if added).

**Important:** `app.mount("/", ...)` will shadow any other route registered AT `/`. Since we don't have a route at exactly `/` (the spine has `/health`, `/capture`, `/graph`, etc. — all prefixed paths), the mount is safe. But the mount must come AFTER all router registrations.

- [ ] **Step 2: verify locally**

```bash
cd frontend && npm run build
cd ../backend && uv run uvicorn app.main:app --port 8000 &
sleep 2
curl -s http://localhost:8000/ | head -5
```

Expected: HTML output containing `<div id="root">`.

Kill the background uvicorn before continuing.

- [ ] **Step 3: commit**

```bash
git add backend/app/main.py
git commit -m "feat(integration): FastAPI serves frontend/dist at root in production"
```

---

## Task 19: frontend CI workflow

**Files:**
- Create: `.github/workflows/frontend-ci.yml`

- [ ] **Step 1: workflow**

```yaml
# .github/workflows/frontend-ci.yml
name: frontend-ci

on:
  push:
    paths:
      - "frontend/**"
      - ".github/workflows/frontend-ci.yml"
  pull_request:
    paths:
      - "frontend/**"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - name: Install
        working-directory: frontend
        run: npm ci
      - name: Lint
        working-directory: frontend
        run: npm run lint
      - name: Test
        working-directory: frontend
        run: npm run test
      - name: Build
        working-directory: frontend
        run: npm run build
```

- [ ] **Step 2: ESLint config**

Add to `frontend/`:

```javascript
// frontend/.eslintrc.cjs
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  ignorePatterns: ["dist", ".eslintrc.cjs"],
  parser: "@typescript-eslint/parser",
  plugins: ["react-refresh"],
  rules: {
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true },
    ],
  },
};
```

- [ ] **Step 3: commit**

```bash
git add .github/workflows/frontend-ci.yml frontend/.eslintrc.cjs
git commit -m "ci(frontend): GitHub Actions for lint + test + build"
```

---

## Done — Plan 3 deliverables

After this plan:

- 5 new backend endpoints: `GET /graph`, `GET /nodes/{table}/{id}`, `GET /gate-items`, `POST /gate-items/{id}/resolve`, `GET /hotspots`, `GET /search`
- React + TypeScript SPA at `frontend/` with: typed API client, SSE hook, GraphProvider state, force-directed Cytoscape canvas, node detail panel, capture bar, gate item list with resolve modal
- Hot spot pulse animation + new-node arrival glow
- Frontend served by FastAPI in production
- Frontend CI (lint + test + build)
- ~25 new tests (5 backend + ~20 frontend)

**Estimated build:** 2-3 weeks for v0.1.

**Deferred to v0.2 (not in this plan):**

- Voice capture in CaptureBar
- Search input UI (the `/search` endpoint exists but has no frontend yet)
- External zoom-in: clicking a Bet node opens its Obsidian path; clicking a Task opens Linear; clicking a CodeChange opens GitHub. (Plan 5 will add the adapter URLs to node props; v0.2 wires the click handlers.)
- Time-travel scrubber, history view
- Agent panel UI (the `/agents` endpoints exist; the UI ships with mobile in Plan 4 or as a v0.2 enhancement)
- React Router for multi-page navigation
- Authenticated multi-user
- Touch gestures / mobile responsiveness (that's Plan 4)
- WebSocket fallback if SSE fails
- Optimistic gate item updates (current implementation re-fetches after every action)

**Open question to resolve before execution:**

The `gigabrain.gate.resolved` event payload from spec §5 is intentionally NOT emitted in this plan's `POST /gate-items/{id}/resolve`. That telemetry path is owned by **Plan 6 (GigaFlow integration)**. If you'd rather emit it now (so GigaFlow integration is a flip-the-flag operation in Plan 6), add an `await bus.publish(...)` call in `gate_items.py:resolve` with a new pydantic event in `app/events/schemas.py`. Either choice is buildable; this plan defers to keep telemetry concerns isolated to Plan 6.
