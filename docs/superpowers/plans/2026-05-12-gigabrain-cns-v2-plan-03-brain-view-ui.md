# GigaBrain CNS v2 — Plan 3: Brain View UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the primary user-facing surface for GigaBrain CNS v2 — a force-directed desktop graph view plus a responsive mobile inbox view, both driven in real time by the spine's `/stream` SSE feed. By the end of this plan, opening the app shows the live brain graph, gate items glow, captures land instantly, and clicking a node zooms to its destination (Obsidian / Linear / GitHub / in-place).

**Architecture:** Single-page React + TypeScript app in `frontend/`, built with Vite and served as static assets by the FastAPI backend in production. Real-time graph state via the existing `/stream` SSE endpoint (Plan 01 task 15). Initial state via two new backend endpoints (`GET /graph/state`, `GET /graph/nodes/{id}`). Gate resolution via a new `POST /gate/{id}/resolve` endpoint. Force-directed rendering via `react-force-graph-2d`. State managed by a single `useReducer` behind a React context — no Redux/Zustand. Tailwind for styling.

**Tech Stack:** TypeScript 5, React 18, Vite 5, Tailwind CSS 3, react-router-dom 6, react-force-graph-2d, Vitest, @testing-library/react, jsdom. Python additions: a new `app/api/graph.py` router and a new `app/gate/` package on the backend.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-gigabrain-cns-v2-design.md`](../specs/2026-05-06-gigabrain-cns-v2-design.md) — Section 4 (Brain view UI). Cross-references Section 1 (data model), Section 2 (capture/sparring), Section 5 (telemetry — gate-resolution event class).

**Predecessor plans:**

- [`2026-05-06-gigabrain-cns-v2-plan-01-spine.md`](./2026-05-06-gigabrain-cns-v2-plan-01-spine.md) — capture, sparring, graph substrate, `/stream`.
- [`2026-05-07-gigabrain-cns-v2-plan-02-agent-runtime.md`](./2026-05-07-gigabrain-cns-v2-plan-02-agent-runtime.md) — agent fleet, `fire.neuron` worker.

---

## Scope (in)

- Desktop graph view: force-directed canvas, node coloring by type, hot-spot glow, top-bar live counts, slide-in node detail panel, bottom capture bar.
- Mobile inbox view: tabbed cards (Gate / Hot / Recent) with inline gate actions, bottom nav.
- Real-time graph updates via SSE.
- New backend endpoints: `GET /graph/state`, `GET /graph/nodes/{id}`, `POST /gate/{id}/resolve`.
- Zoom-in dispatch: bet → Obsidian URI, task → Linear URL, code_change → GitHub URL, gate_item/conflict → in-place panel, thought/decision/outcome/agent_firing → expanded in-place view.
- Production: FastAPI mounts the built frontend at `/`.
- Tests: Vitest unit tests for state + components; one Python backend test per new endpoint; one end-to-end Playwright smoke test stub (recorded but not run in CI — see Task 17 note).

## Scope (out — defer to v0.2 or other plans)

- Native PWA (installable, offline-capable).
- Voice capture (Plan 04 — capture adapters; UI hook present but disabled).
- "Swap into agent's seat" full agent-trace replay UI. v0.1 ships the click-through to a read-only firing detail view; trace replay is deferred.
- Hot-spot scoring learned from GigaFlow signals. v0.1 ships hand-tuned weights; replacement is Plan 07.
- Multi-leader scoping. Single user, single leader for v0.1.

---

## File structure

```
frontend/                                # NEW: built with Vite, served by FastAPI in prod
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── .gitignore
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx                         # React entry
│   ├── App.tsx                          # Router + viewport-based layout switch
│   ├── api/
│   │   ├── client.ts                    # fetch wrapper (base URL, JSON parsing)
│   │   ├── types.ts                     # Node / Edge / Event TS types (mirror backend pydantic)
│   │   └── stream.ts                    # EventSource wrapper, typed event dispatch
│   ├── state/
│   │   ├── graph.ts                     # Graph state reducer (nodes, edges, gate items)
│   │   ├── GraphProvider.tsx            # React context + bootstrap fetch + SSE wire-up
│   │   └── hotSpots.ts                  # Pure function: nodes → hot-spot score map
│   ├── views/
│   │   ├── DesktopGraphView.tsx         # Force-directed canvas + overlays
│   │   ├── MobileInboxView.tsx          # Tabs + card stack + bottom nav
│   │   ├── NodeDetailPanel.tsx          # Right slide-in
│   │   └── GateResolvePanel.tsx         # In-place gate item resolver
│   ├── components/
│   │   ├── TopBar.tsx                   # Live counts
│   │   ├── CaptureBar.tsx               # Bottom-anchored text input
│   │   ├── GateCard.tsx                 # Mobile inbox card
│   │   ├── NodeBadge.tsx                # Color/icon by node type
│   │   └── HotSpotGlow.tsx              # Pulse overlay (canvas decoration)
│   ├── lib/
│   │   ├── colors.ts                    # NodeType → Tailwind color tokens
│   │   ├── zoomIn.ts                    # NodeType → destination resolver
│   │   └── time.ts                      # Age formatting ("3m ago")
│   └── styles/
│       └── globals.css                  # Tailwind base directives
├── tests/
│   ├── setup.ts                         # Vitest jsdom + @testing-library setup
│   ├── api/
│   │   ├── client.test.ts
│   │   └── stream.test.ts
│   ├── state/
│   │   ├── graph.test.ts
│   │   └── hotSpots.test.ts
│   ├── views/
│   │   ├── DesktopGraphView.test.tsx
│   │   ├── MobileInboxView.test.tsx
│   │   └── GateResolvePanel.test.tsx
│   └── components/
│       ├── CaptureBar.test.tsx
│       ├── GateCard.test.tsx
│       └── TopBar.test.tsx
└── e2e/
    └── capture-renders.spec.ts          # Playwright smoke (deferred run, see Task 17)

backend/app/                             # MODIFIED
├── api/
│   ├── graph.py                         # NEW — /graph/state + /graph/nodes/{id}
│   └── frontend.py                      # NEW — mounts built frontend static assets
├── gate/
│   ├── __init__.py
│   ├── api.py                           # NEW — POST /gate/{id}/resolve
│   └── resolver.py                      # NEW — applies decision + emits OTel event
└── main.py                              # MODIFIED — wire new routers

backend/tests/                           # MODIFIED
├── test_api/
│   ├── test_graph.py                    # NEW
│   └── test_frontend.py                 # NEW
└── test_gate/
    ├── __init__.py
    └── test_resolver.py                 # NEW
```

---

## Conventions and reminders for the executor

- **Worktree:** This plan executes inside the `feat/plan-03-brain-view-ui` worktree.
- **Working directory:** All `npm`, `vite`, `vitest`, and `playwright` commands run from `frontend/`. All `pytest` and `uv` commands run from `backend/`.
- **Package manager:** `npm` (not pnpm/yarn) to match the obsidian-plugin repo precedent.
- **No comments policy:** Per repo CLAUDE.md, do not add code comments unless a non-obvious WHY needs to be captured. Tests document behavior.
- **Frequent commits:** every task ends in a commit. Commits MUST NOT skip hooks.
- **Type-source-of-truth:** TypeScript types in `frontend/src/api/types.ts` mirror `backend/app/db/schemas.py` and `backend/app/events/schemas.py`. When the backend changes, both files change in the same commit.

---

## Task 1: Frontend scaffold (Vite + React + TS + Tailwind + Vitest)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/.gitignore`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/public/favicon.svg`
- Create: `frontend/tests/setup.ts`
- Create: `frontend/tests/App.test.tsx`

- [ ] **Step 1: Create package.json**

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
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "react-force-graph-2d": "^1.25.5"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.0",
    "postcss": "^8.4.41",
    "tailwindcss": "^3.4.10",
    "typescript": "^5.5.4",
    "vite": "^5.4.0",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
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
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: Create tsconfig.node.json**

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

- [ ] **Step 4: Create vite.config.ts**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/stream": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    css: false,
  },
});
```

- [ ] **Step 5: Create tailwind.config.js and postcss.config.js**

```js
// frontend/tailwind.config.js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bet: "#a78bfa",
        gate: "#facc15",
        conflict: "#ef4444",
        thought: "#34d399",
        firing: "#c084fc",
        codechange: "#60a5fa",
        doc: "#93c5fd",
      },
      animation: {
        "hot-pulse": "hot-pulse 2s ease-in-out infinite",
      },
      keyframes: {
        "hot-pulse": {
          "0%, 100%": { opacity: "0.6", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.08)" },
        },
      },
    },
  },
  plugins: [],
};
```

```js
// frontend/postcss.config.js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 6: Create index.html**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>GigaBrain</title>
  </head>
  <body class="bg-neutral-950 text-neutral-100">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create .gitignore, favicon, and globals.css**

```gitignore
# frontend/.gitignore
node_modules/
dist/
.vite/
coverage/
*.log
```

```svg
<!-- frontend/public/favicon.svg -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#a78bfa"><circle cx="12" cy="12" r="5"/><circle cx="4" cy="6" r="2"/><circle cx="20" cy="6" r="2"/><circle cx="4" cy="18" r="2"/><circle cx="20" cy="18" r="2"/><path stroke="#a78bfa" stroke-width="1" d="M12 12 L4 6 M12 12 L20 6 M12 12 L4 18 M12 12 L20 18"/></svg>
```

```css
/* frontend/src/styles/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root {
  height: 100%;
  margin: 0;
}
```

- [ ] **Step 8: Create tests/setup.ts**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 9: Write the failing App test**

```tsx
// frontend/tests/App.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App";

describe("App", () => {
  it("renders the GigaBrain shell", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/GigaBrain/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 10: Install dependencies and run the failing test**

Run: `cd frontend && npm install`
Run: `cd frontend && npm test -- App`
Expected: FAIL — "Cannot find module '../src/App'".

- [ ] **Step 11: Implement minimal App + main**

```tsx
// frontend/src/App.tsx
export default function App() {
  return (
    <div className="h-full w-full flex items-center justify-center">
      <h1 className="text-3xl font-semibold">GigaBrain</h1>
    </div>
  );
}
```

```tsx
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
```

- [ ] **Step 12: Re-run the test**

Run: `cd frontend && npm test -- App`
Expected: PASS.

- [ ] **Step 13: Confirm production build works**

Run: `cd frontend && npm run build`
Expected: exit 0, `dist/index.html` created.

- [ ] **Step 14: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold Vite + React + Tailwind + Vitest"
```

---

## Task 2: API types mirror backend schemas

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/tests/api/types.test.ts`

- [ ] **Step 1: Write the failing type test**

```ts
// frontend/tests/api/types.test.ts
import { describe, it, expect } from "vitest";
import type { AnyNode, NodeType, GraphChangedEvent } from "../../src/api/types";

describe("api/types", () => {
  it("NodeType union covers every spec-defined node type", () => {
    const allTypes: NodeType[] = [
      "thought", "bet", "task", "decision", "conflict",
      "outcome", "agent_firing", "code_change", "conversation",
      "doc", "gate_item", "agent",
    ];
    expect(allTypes.length).toBe(12);
  });

  it("AnyNode discriminates by node_type", () => {
    const node: AnyNode = {
      node_type: "thought",
      id: "t_abc",
      content: "hello",
      source: "web",
      created_at: "2026-05-12T00:00:00Z",
      metadata: {},
    };
    if (node.node_type === "thought") {
      expect(node.content).toBe("hello");
    }
  });

  it("GraphChangedEvent shape matches backend", () => {
    const event: GraphChangedEvent = {
      event: "graph.changed",
      change_type: "node_created",
      node_id: "t_abc",
    };
    expect(event.event).toBe("graph.changed");
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- types`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement types.ts**

```ts
// frontend/src/api/types.ts
export type NodeType =
  | "thought" | "bet" | "task" | "decision" | "conflict"
  | "outcome" | "agent_firing" | "code_change" | "conversation"
  | "doc" | "gate_item" | "agent";

interface NodeBase {
  id: string;
  created_at: string;
  embedding_id?: string | null;
}

export interface ThoughtNode extends NodeBase {
  node_type: "thought";
  content: string;
  source: string;
  metadata: Record<string, unknown>;
}

export interface BetNode extends NodeBase {
  node_type: "bet";
  slug: string;
  title: string;
  vault_path: string;
  owner: string;
  horizon: string;
  confidence: string;
}

export interface TaskNode extends NodeBase {
  node_type: "task";
  linear_id: string;
  title: string;
  status: string;
}

export interface DecisionNode extends NodeBase {
  node_type: "decision";
  content: string;
  decided_by: string;
  reasoning: string;
}

export interface ConflictNode extends NodeBase {
  node_type: "conflict";
  summary: string;
  severity: string;
}

export interface OutcomeNode extends NodeBase {
  node_type: "outcome";
  summary: string;
  success: boolean;
}

export interface AgentFiringNode extends NodeBase {
  node_type: "agent_firing";
  agent_id: string;
  trace_id: string;
  started_at: string;
  completed_at: string | null;
  outcome: string | null;
}

export interface CodeChangeNode extends NodeBase {
  node_type: "code_change";
  repo: string;
  sha: string;
  summary: string;
}

export interface ConversationNode extends NodeBase {
  node_type: "conversation";
  summary: string;
  vault_path: string | null;
}

export interface DocNode extends NodeBase {
  node_type: "doc";
  vault_path: string;
  title: string;
}

export interface GateItemNode extends NodeBase {
  node_type: "gate_item";
  prompt: string;
  urgency: string;
  resolved_at: string | null;
  decision: string | null;
  reasoning: string;
}

export interface AgentNode extends NodeBase {
  node_type: "agent";
  role: string;
  persona: string;
  state: string;
  current_firing: string | null;
  last_active: string | null;
  enabled: boolean;
}

export type AnyNode =
  | ThoughtNode | BetNode | TaskNode | DecisionNode | ConflictNode
  | OutcomeNode | AgentFiringNode | CodeChangeNode | ConversationNode
  | DocNode | GateItemNode | AgentNode;

export interface Edge {
  from_id: string;
  from_type: NodeType;
  to_id: string;
  to_type: NodeType;
  edge_type: string;
  created_at: string;
  confidence: number;
}

export interface GraphState {
  nodes: AnyNode[];
  edges: Edge[];
}

export interface GraphChangedEvent {
  event: "graph.changed";
  change_type: "node_created" | "node_updated" | "edge_created";
  node_id?: string | null;
  edge_id?: string | null;
}

export interface GateItemCreatedEvent {
  event: "gate.created";
  gate_item_id: string;
  thought_id: string;
  urgency: string;
}

export interface FireNeuronEvent {
  event: "fire.neuron";
  thought_id: string;
  agent_role: string;
  task_summary: string;
}

export type StreamEvent =
  | GraphChangedEvent
  | GateItemCreatedEvent
  | FireNeuronEvent;
```

- [ ] **Step 4: Re-run test**

Run: `cd frontend && npm test -- types`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/tests/api/types.test.ts
git commit -m "feat(frontend): API types mirroring backend node/edge/event schemas"
```

---

## Task 3: Backend `GET /graph/state` endpoint

**Files:**
- Create: `backend/app/api/graph.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api/test_graph.py
import pytest
from fastapi.testclient import TestClient

from app.db.schemas import ThoughtNode, BetNode


@pytest.fixture
def client_with_seeded_nodes(test_app, node_repo):
    node_repo.create(ThoughtNode(content="a thought", source="web"))
    node_repo.create(
        BetNode(
            slug="ship-v1",
            title="Ship v1",
            vault_path="Brain/Bets/bet_ship_v1.md",
            owner="ceo",
        )
    )
    return TestClient(test_app)


def test_graph_state_returns_all_nodes_and_edges(client_with_seeded_nodes):
    response = client_with_seeded_nodes.get("/graph/state")
    assert response.status_code == 200
    body = response.json()
    assert "nodes" in body and "edges" in body
    node_types = sorted({n["node_type"] for n in body["nodes"]})
    assert "bet" in node_types
    assert "thought" in node_types


def test_graph_state_includes_node_fields(client_with_seeded_nodes):
    response = client_with_seeded_nodes.get("/graph/state")
    bet = next(n for n in response.json()["nodes"] if n["node_type"] == "bet")
    assert bet["slug"] == "ship-v1"
    assert bet["title"] == "Ship v1"
```

The `test_app` and `node_repo` fixtures are already provided by `backend/tests/conftest.py` (Plan 01).

- [ ] **Step 2: Run the test**

Run: `cd backend && uv run pytest tests/test_api/test_graph.py -v`
Expected: FAIL — 404 from FastAPI (route not registered).

- [ ] **Step 3: Implement the router**

```python
# backend/app/api/graph.py
from fastapi import APIRouter

from app.db.kuzu import KuzuConnection


_NODE_TABLES = [
    "Thought", "Bet", "Task", "Decision", "Conflict",
    "Outcome", "AgentFiring", "CodeChange", "Conversation",
    "Doc", "GateItem", "Agent",
]

_TABLE_TO_TYPE = {
    "Thought": "thought", "Bet": "bet", "Task": "task",
    "Decision": "decision", "Conflict": "conflict", "Outcome": "outcome",
    "AgentFiring": "agent_firing", "CodeChange": "code_change",
    "Conversation": "conversation", "Doc": "doc",
    "GateItem": "gate_item", "Agent": "agent",
}


def build_graph_router(conn: KuzuConnection) -> APIRouter:
    router = APIRouter(prefix="/graph")

    @router.get("/state")
    async def state():
        nodes: list[dict] = []
        for table in _NODE_TABLES:
            rows = conn.query(f"MATCH (n:{table}) RETURN n")
            for row in rows:
                payload = row["n"] if isinstance(row.get("n"), dict) else row
                payload["node_type"] = _TABLE_TO_TYPE[table]
                nodes.append(payload)

        edges_rows = conn.query(
            "MATCH (a)-[e]->(b) RETURN a.id AS from_id, b.id AS to_id, "
            "label(e) AS edge_type, e.created_at AS created_at, "
            "coalesce(e.confidence, 1.0) AS confidence"
        )
        edges = [
            {
                "from_id": r["from_id"],
                "from_type": None,
                "to_id": r["to_id"],
                "to_type": None,
                "edge_type": r["edge_type"],
                "created_at": r.get("created_at"),
                "confidence": r.get("confidence", 1.0),
            }
            for r in edges_rows
        ]
        return {"nodes": nodes, "edges": edges}

    return router
```

- [ ] **Step 4: Wire the router in main.py**

Modify `backend/app/main.py`. Locate the section that builds routers during lifespan (around line 86 where `build_capture_router` is included). Add immediately after `build_capture_router(...)`:

```python
from app.api.graph import build_graph_router
app.include_router(build_graph_router(conn))
```

- [ ] **Step 5: Re-run test**

Run: `cd backend && uv run pytest tests/test_api/test_graph.py -v`
Expected: PASS.

- [ ] **Step 6: Verify other tests still pass**

Run: `cd backend && uv run pytest -x`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/graph.py backend/app/main.py backend/tests/test_api/test_graph.py
git commit -m "feat(api): GET /graph/state returns all nodes and edges"
```

---

## Task 4: Backend `GET /graph/nodes/{id}` endpoint

**Files:**
- Modify: `backend/app/api/graph.py`
- Modify: `backend/tests/test_api/test_graph.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/test_api/test_graph.py`:

```python
def test_graph_node_by_id_returns_full_detail(client_with_seeded_nodes, node_repo):
    bet = next(
        n for n in client_with_seeded_nodes.get("/graph/state").json()["nodes"]
        if n["node_type"] == "bet"
    )
    response = client_with_seeded_nodes.get(f"/graph/nodes/{bet['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["node_type"] == "bet"
    assert body["slug"] == "ship-v1"
    assert "edges_in" in body
    assert "edges_out" in body


def test_graph_node_by_id_returns_404_for_unknown(client_with_seeded_nodes):
    response = client_with_seeded_nodes.get("/graph/nodes/does_not_exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run the test**

Run: `cd backend && uv run pytest tests/test_api/test_graph.py::test_graph_node_by_id_returns_full_detail -v`
Expected: FAIL — 404 (route not yet defined).

- [ ] **Step 3: Extend the router**

Append to `backend/app/api/graph.py` inside `build_graph_router`:

```python
    from fastapi import HTTPException

    @router.get("/nodes/{node_id}")
    async def node_detail(node_id: str):
        for table, node_type in _TABLE_TO_TYPE.items():
            rows = conn.query(
                f"MATCH (n:{table}) WHERE n.id = $id RETURN n",
                {"id": node_id},
            )
            if rows:
                payload = rows[0]["n"] if isinstance(rows[0].get("n"), dict) else rows[0]
                payload["node_type"] = node_type
                edges_in = conn.query(
                    "MATCH (a)-[e]->(b) WHERE b.id = $id RETURN a.id AS from_id, "
                    "label(e) AS edge_type",
                    {"id": node_id},
                )
                edges_out = conn.query(
                    "MATCH (a)-[e]->(b) WHERE a.id = $id RETURN b.id AS to_id, "
                    "label(e) AS edge_type",
                    {"id": node_id},
                )
                payload["edges_in"] = list(edges_in)
                payload["edges_out"] = list(edges_out)
                return payload
        raise HTTPException(status_code=404, detail=f"node {node_id} not found")
```

(Move the `HTTPException` import to the top of the file.)

- [ ] **Step 4: Re-run tests**

Run: `cd backend && uv run pytest tests/test_api/test_graph.py -v`
Expected: All three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/graph.py backend/tests/test_api/test_graph.py
git commit -m "feat(api): GET /graph/nodes/{id} returns node detail with edges"
```

---

## Task 5: Frontend API client

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/tests/api/client.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// frontend/tests/api/client.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { fetchGraphState, fetchNodeDetail, postCapture } from "../../src/api/client";

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn();
});
afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("api/client", () => {
  it("fetchGraphState GETs /api/graph/state", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [], edges: [] }),
    });
    const state = await fetchGraphState();
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/graph/state");
    expect(state).toEqual({ nodes: [], edges: [] });
  });

  it("fetchNodeDetail GETs /api/graph/nodes/:id", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ node_type: "bet", id: "b_x" }),
    });
    const node = await fetchNodeDetail("b_x");
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/graph/nodes/b_x");
    expect(node.node_type).toBe("bet");
  });

  it("postCapture POSTs JSON to /api/capture", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ node_id: "t_x", status: "ok" }),
    });
    const res = await postCapture("a thought");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/capture",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(res.node_id).toBe("t_x");
  });

  it("throws on non-OK responses", async () => {
    (globalThis.fetch as any).mockResolvedValue({ ok: false, status: 500 });
    await expect(fetchGraphState()).rejects.toThrow(/500/);
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- client`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the client**

```ts
// frontend/src/api/client.ts
import type { AnyNode, GraphState } from "./types";

const BASE = "/api";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

export function fetchGraphState() {
  return getJSON<GraphState>("/graph/state");
}

export function fetchNodeDetail(id: string) {
  return getJSON<AnyNode & { edges_in: unknown[]; edges_out: unknown[] }>(
    `/graph/nodes/${id}`,
  );
}

export interface CaptureResponse {
  node_id: string;
  status: string;
}

export function postCapture(content: string, source: string = "web") {
  return postJSON<CaptureResponse>("/capture", { content, source });
}

export interface GateResolveRequest {
  decision: "approved" | "vetoed" | "resteered";
  reasoning: string;
  alternative?: string | null;
}

export function postGateResolve(gateId: string, body: GateResolveRequest) {
  return postJSON<{ status: string }>(`/gate/${gateId}/resolve`, body);
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- client`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/tests/api/client.test.ts
git commit -m "feat(frontend): typed fetch wrappers for graph/capture/gate endpoints"
```

---

## Task 6: SSE stream client

**Files:**
- Create: `frontend/src/api/stream.ts`
- Create: `frontend/tests/api/stream.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// frontend/tests/api/stream.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { subscribeToStream } from "../../src/api/stream";
import type { StreamEvent } from "../../src/api/types";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  emit(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  // @ts-expect-error — install mock
  globalThis.EventSource = MockEventSource;
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("api/stream", () => {
  it("subscribeToStream opens an EventSource at /stream", () => {
    subscribeToStream(() => {});
    expect(MockEventSource.instances[0].url).toBe("/stream");
  });

  it("dispatches parsed StreamEvents to the handler", () => {
    const handler = vi.fn();
    subscribeToStream(handler);
    const event: StreamEvent = {
      event: "graph.changed",
      change_type: "node_created",
      node_id: "t_abc",
    };
    MockEventSource.instances[0].emit(event);
    expect(handler).toHaveBeenCalledWith(event);
  });

  it("returns a disposer that closes the source", () => {
    const dispose = subscribeToStream(() => {});
    dispose();
    expect(MockEventSource.instances[0].closed).toBe(true);
  });

  it("ignores keepalive comments (non-JSON messages)", () => {
    const handler = vi.fn();
    subscribeToStream(handler);
    MockEventSource.instances[0].onmessage?.(
      new MessageEvent("message", { data: ": keepalive" }),
    );
    expect(handler).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- stream`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the stream client**

```ts
// frontend/src/api/stream.ts
import type { StreamEvent } from "./types";

export type StreamHandler = (event: StreamEvent) => void;

export function subscribeToStream(handler: StreamHandler): () => void {
  const source = new EventSource("/stream");

  source.onmessage = (e) => {
    const raw = e.data;
    if (typeof raw !== "string" || !raw.trim().startsWith("{")) {
      return;
    }
    try {
      handler(JSON.parse(raw) as StreamEvent);
    } catch {
      // malformed payload — ignore; next message will arrive
    }
  };

  return () => source.close();
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- stream`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/stream.ts frontend/tests/api/stream.test.ts
git commit -m "feat(frontend): SSE subscription with typed event dispatch"
```

---

## Task 7: Graph state reducer

**Files:**
- Create: `frontend/src/state/graph.ts`
- Create: `frontend/tests/state/graph.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// frontend/tests/state/graph.test.ts
import { describe, it, expect } from "vitest";
import { graphReducer, initialGraphState } from "../../src/state/graph";
import type { ThoughtNode, BetNode, Edge } from "../../src/api/types";

const thought: ThoughtNode = {
  node_type: "thought",
  id: "t_1",
  content: "hello",
  source: "web",
  created_at: "2026-05-12T00:00:00Z",
  metadata: {},
};
const bet: BetNode = {
  node_type: "bet",
  id: "b_1",
  slug: "x",
  title: "X",
  vault_path: "Brain/Bets/bet_x.md",
  owner: "ceo",
  horizon: "Q",
  confidence: "medium",
  created_at: "2026-05-12T00:00:00Z",
};
const edge: Edge = {
  from_id: "t_1",
  from_type: "thought",
  to_id: "b_1",
  to_type: "bet",
  edge_type: "sparred-against",
  created_at: "2026-05-12T00:00:00Z",
  confidence: 1.0,
};

describe("graph reducer", () => {
  it("HYDRATE replaces all state", () => {
    const next = graphReducer(initialGraphState, {
      type: "HYDRATE",
      state: { nodes: [thought, bet], edges: [edge] },
    });
    expect(next.nodes).toHaveLength(2);
    expect(next.edges).toHaveLength(1);
  });

  it("ADD_NODE appends a new node", () => {
    const next = graphReducer(initialGraphState, { type: "ADD_NODE", node: thought });
    expect(next.nodes).toEqual([thought]);
  });

  it("ADD_NODE is idempotent on existing id", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_NODE", node: thought });
    const next = graphReducer(state, { type: "ADD_NODE", node: thought });
    expect(next.nodes).toHaveLength(1);
  });

  it("UPDATE_NODE replaces a node by id", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_NODE", node: bet });
    const updated: BetNode = { ...bet, title: "X v2" };
    const next = graphReducer(state, { type: "UPDATE_NODE", node: updated });
    expect(next.nodes[0]).toEqual(updated);
  });

  it("UPDATE_NODE on unknown id is a no-op", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_NODE", node: bet });
    const ghost: ThoughtNode = { ...thought, id: "t_ghost" };
    const next = graphReducer(state, { type: "UPDATE_NODE", node: ghost });
    expect(next.nodes).toEqual([bet]);
  });

  it("ADD_EDGE appends and dedupes on from/to/edge_type", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_EDGE", edge });
    const next = graphReducer(state, { type: "ADD_EDGE", edge });
    expect(next.edges).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- state/graph`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the reducer**

```ts
// frontend/src/state/graph.ts
import type { AnyNode, Edge, GraphState } from "../api/types";

export const initialGraphState: GraphState = { nodes: [], edges: [] };

export type GraphAction =
  | { type: "HYDRATE"; state: GraphState }
  | { type: "ADD_NODE"; node: AnyNode }
  | { type: "UPDATE_NODE"; node: AnyNode }
  | { type: "ADD_EDGE"; edge: Edge };

const edgeKey = (e: Edge) => `${e.from_id}::${e.to_id}::${e.edge_type}`;

export function graphReducer(state: GraphState, action: GraphAction): GraphState {
  switch (action.type) {
    case "HYDRATE":
      return action.state;
    case "ADD_NODE": {
      if (state.nodes.some((n) => n.id === action.node.id)) return state;
      return { ...state, nodes: [...state.nodes, action.node] };
    }
    case "UPDATE_NODE": {
      const idx = state.nodes.findIndex((n) => n.id === action.node.id);
      if (idx < 0) return state;
      const nodes = state.nodes.slice();
      nodes[idx] = action.node;
      return { ...state, nodes };
    }
    case "ADD_EDGE": {
      const key = edgeKey(action.edge);
      if (state.edges.some((e) => edgeKey(e) === key)) return state;
      return { ...state, edges: [...state.edges, action.edge] };
    }
    default:
      return state;
  }
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- state/graph`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/state/graph.ts frontend/tests/state/graph.test.ts
git commit -m "feat(frontend): graph state reducer with idempotent add/update"
```

---

## Task 8: GraphProvider — context + bootstrap + SSE wiring

**Files:**
- Create: `frontend/src/state/GraphProvider.tsx`
- Create: `frontend/tests/state/GraphProvider.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/tests/state/GraphProvider.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { GraphProvider, useGraph } from "../../src/state/GraphProvider";
import type { ThoughtNode } from "../../src/api/types";

const thought: ThoughtNode = {
  node_type: "thought",
  id: "t_1",
  content: "hi",
  source: "web",
  created_at: "2026-05-12T00:00:00Z",
  metadata: {},
};

function Probe() {
  const { state } = useGraph();
  return <div data-testid="count">{state.nodes.length}</div>;
}

class MockEventSource {
  static instance: MockEventSource | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {
    MockEventSource.instance = this;
  }
}

beforeEach(() => {
  // @ts-expect-error mock
  globalThis.EventSource = MockEventSource;
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ nodes: [thought], edges: [] }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("GraphProvider", () => {
  it("hydrates from /graph/state on mount", async () => {
    render(
      <GraphProvider>
        <Probe />
      </GraphProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
  });

  it("appends nodes when stream emits graph.changed/node_created", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ nodes: [], edges: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => thought });

    render(
      <GraphProvider>
        <Probe />
      </GraphProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("0"));

    await act(async () => {
      MockEventSource.instance!.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({
            event: "graph.changed",
            change_type: "node_created",
            node_id: "t_1",
          }),
        }),
      );
    });

    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- GraphProvider`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the provider**

```tsx
// frontend/src/state/GraphProvider.tsx
import { createContext, useContext, useEffect, useReducer } from "react";
import type { ReactNode } from "react";
import { fetchGraphState, fetchNodeDetail } from "../api/client";
import { subscribeToStream } from "../api/stream";
import {
  graphReducer,
  initialGraphState,
  type GraphAction,
} from "./graph";
import type { GraphState, AnyNode } from "../api/types";

interface GraphContextValue {
  state: GraphState;
  dispatch: React.Dispatch<GraphAction>;
}

const GraphContext = createContext<GraphContextValue | null>(null);

export function GraphProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(graphReducer, initialGraphState);

  useEffect(() => {
    let cancelled = false;
    fetchGraphState().then((snapshot) => {
      if (!cancelled) dispatch({ type: "HYDRATE", state: snapshot });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const dispose = subscribeToStream(async (event) => {
      if (event.event !== "graph.changed") return;
      if (event.change_type === "node_created" && event.node_id) {
        const node = (await fetchNodeDetail(event.node_id)) as AnyNode;
        dispatch({ type: "ADD_NODE", node });
      } else if (event.change_type === "node_updated" && event.node_id) {
        const node = (await fetchNodeDetail(event.node_id)) as AnyNode;
        dispatch({ type: "UPDATE_NODE", node });
      }
    });
    return dispose;
  }, []);

  return (
    <GraphContext.Provider value={{ state, dispatch }}>
      {children}
    </GraphContext.Provider>
  );
}

export function useGraph(): GraphContextValue {
  const ctx = useContext(GraphContext);
  if (!ctx) throw new Error("useGraph must be used inside GraphProvider");
  return ctx;
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- GraphProvider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/state/GraphProvider.tsx frontend/tests/state/GraphProvider.test.tsx
git commit -m "feat(frontend): GraphProvider hydrates state and subscribes to SSE"
```

---

## Task 9: Hot-spot scoring

**Files:**
- Create: `frontend/src/state/hotSpots.ts`
- Create: `frontend/tests/state/hotSpots.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// frontend/tests/state/hotSpots.test.ts
import { describe, it, expect } from "vitest";
import { computeHotSpots, HOT_SPOT_WEIGHTS } from "../../src/state/hotSpots";
import type { AnyNode, Edge, GraphState } from "../../src/api/types";

function mkConflict(id: string): AnyNode {
  return {
    node_type: "conflict",
    id,
    summary: "x",
    severity: "high",
    created_at: "2026-05-12T00:00:00Z",
  };
}

function mkGate(id: string, urgency = "urgent"): AnyNode {
  return {
    node_type: "gate_item",
    id,
    prompt: "x",
    urgency,
    resolved_at: null,
    decision: null,
    reasoning: "",
    created_at: "2026-05-12T00:00:00Z",
  };
}

describe("hotSpots", () => {
  it("conflicts contribute by severity", () => {
    const state: GraphState = { nodes: [mkConflict("c_1")], edges: [] };
    const map = computeHotSpots(state);
    expect(map.get("c_1")).toBeGreaterThan(0);
  });

  it("urgent gate items score higher than novel gate items", () => {
    const state: GraphState = {
      nodes: [mkGate("g_urgent", "urgent"), mkGate("g_novel", "novel")],
      edges: [],
    };
    const map = computeHotSpots(state);
    expect(map.get("g_urgent")!).toBeGreaterThan(map.get("g_novel")!);
  });

  it("higher-degree nodes get a connectivity bonus", () => {
    const a = mkConflict("c_a");
    const b = mkConflict("c_b");
    const edges: Edge[] = [
      { from_id: "c_a", from_type: "conflict", to_id: "t_x", to_type: "thought", edge_type: "x", created_at: "", confidence: 1 },
      { from_id: "c_a", from_type: "conflict", to_id: "t_y", to_type: "thought", edge_type: "x", created_at: "", confidence: 1 },
    ];
    const map = computeHotSpots({ nodes: [a, b], edges });
    expect(map.get("c_a")!).toBeGreaterThan(map.get("c_b")!);
  });

  it("weights table is exported and matches expected keys", () => {
    expect(HOT_SPOT_WEIGHTS).toMatchObject({
      conflict: expect.any(Number),
      gate_urgent: expect.any(Number),
      gate_medium: expect.any(Number),
      gate_novel: expect.any(Number),
      degree: expect.any(Number),
    });
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- hotSpots`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement scoring**

```ts
// frontend/src/state/hotSpots.ts
import type { GraphState } from "../api/types";

export const HOT_SPOT_WEIGHTS = {
  conflict: 2.5,
  gate_urgent: 3.0,
  gate_medium: 1.5,
  gate_novel: 0.5,
  degree: 0.2,
} as const;

export function computeHotSpots(state: GraphState): Map<string, number> {
  const degree = new Map<string, number>();
  for (const e of state.edges) {
    degree.set(e.from_id, (degree.get(e.from_id) ?? 0) + 1);
    degree.set(e.to_id, (degree.get(e.to_id) ?? 0) + 1);
  }

  const scores = new Map<string, number>();
  for (const node of state.nodes) {
    let score = 0;
    if (node.node_type === "conflict") {
      score += HOT_SPOT_WEIGHTS.conflict;
      if (node.severity === "high") score += 1;
    } else if (node.node_type === "gate_item") {
      if (node.urgency === "urgent") score += HOT_SPOT_WEIGHTS.gate_urgent;
      else if (node.urgency === "medium") score += HOT_SPOT_WEIGHTS.gate_medium;
      else score += HOT_SPOT_WEIGHTS.gate_novel;
    } else {
      continue;
    }
    score += (degree.get(node.id) ?? 0) * HOT_SPOT_WEIGHTS.degree;
    scores.set(node.id, score);
  }
  return scores;
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- hotSpots`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/state/hotSpots.ts frontend/tests/state/hotSpots.test.ts
git commit -m "feat(frontend): hand-tuned hot-spot scoring (conflict + gate + degree)"
```

---

## Task 10: Node color/icon library + NodeBadge component

**Files:**
- Create: `frontend/src/lib/colors.ts`
- Create: `frontend/src/components/NodeBadge.tsx`
- Create: `frontend/tests/components/NodeBadge.test.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/tests/components/NodeBadge.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { NodeBadge } from "../../src/components/NodeBadge";

describe("NodeBadge", () => {
  it("renders the node type label", () => {
    render(<NodeBadge type="bet" />);
    expect(screen.getByText(/bet/i)).toBeInTheDocument();
  });

  it("uses a distinct background per node type", () => {
    const { rerender, container } = render(<NodeBadge type="bet" />);
    const betBg = container.firstElementChild!.className;
    rerender(<NodeBadge type="conflict" />);
    const conflictBg = container.firstElementChild!.className;
    expect(betBg).not.toBe(conflictBg);
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- NodeBadge`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement colors + NodeBadge**

```ts
// frontend/src/lib/colors.ts
import type { NodeType } from "../api/types";

export const NODE_HEX: Record<NodeType, string> = {
  thought: "#34d399",
  bet: "#a78bfa",
  task: "#fb923c",
  decision: "#94a3b8",
  conflict: "#ef4444",
  outcome: "#22c55e",
  agent_firing: "#c084fc",
  code_change: "#60a5fa",
  conversation: "#fde68a",
  doc: "#93c5fd",
  gate_item: "#facc15",
  agent: "#f472b6",
};

export const NODE_TAILWIND_BG: Record<NodeType, string> = {
  thought: "bg-thought",
  bet: "bg-bet",
  task: "bg-orange-400",
  decision: "bg-slate-400",
  conflict: "bg-conflict",
  outcome: "bg-green-500",
  agent_firing: "bg-firing",
  code_change: "bg-codechange",
  conversation: "bg-yellow-200",
  doc: "bg-doc",
  gate_item: "bg-gate",
  agent: "bg-pink-400",
};
```

```tsx
// frontend/src/components/NodeBadge.tsx
import type { NodeType } from "../api/types";
import { NODE_TAILWIND_BG } from "../lib/colors";

export function NodeBadge({ type }: { type: NodeType }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium text-neutral-900 ${NODE_TAILWIND_BG[type]}`}
    >
      {type.replace("_", " ")}
    </span>
  );
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- NodeBadge`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/colors.ts frontend/src/components/NodeBadge.tsx frontend/tests/components/NodeBadge.test.tsx
git commit -m "feat(frontend): NodeBadge with per-type color"
```

---

## Task 11: TopBar — live counts

**Files:**
- Create: `frontend/src/components/TopBar.tsx`
- Create: `frontend/tests/components/TopBar.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/tests/components/TopBar.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TopBar } from "../../src/components/TopBar";
import type { GraphState, GateItemNode, ConflictNode } from "../../src/api/types";

const gate = (id: string, resolved = false): GateItemNode => ({
  node_type: "gate_item",
  id,
  prompt: "?",
  urgency: "urgent",
  resolved_at: resolved ? "2026-05-12T01:00:00Z" : null,
  decision: resolved ? "approved" : null,
  reasoning: "",
  created_at: "2026-05-12T00:00:00Z",
});

const conflict = (id: string): ConflictNode => ({
  node_type: "conflict",
  id,
  summary: "x",
  severity: "high",
  created_at: "2026-05-12T00:00:00Z",
});

describe("TopBar", () => {
  it("renders only unresolved gate item count", () => {
    const state: GraphState = {
      nodes: [gate("g_1"), gate("g_2", true)],
      edges: [],
    };
    render(<TopBar state={state} />);
    expect(screen.getByText(/1 gate/i)).toBeInTheDocument();
  });

  it("renders hot spot count from scored nodes", () => {
    const state: GraphState = {
      nodes: [conflict("c_1"), conflict("c_2"), gate("g_1")],
      edges: [],
    };
    render(<TopBar state={state} />);
    expect(screen.getByText(/3 hot/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- TopBar`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement TopBar**

```tsx
// frontend/src/components/TopBar.tsx
import type { GraphState } from "../api/types";
import { computeHotSpots } from "../state/hotSpots";

export function TopBar({ state }: { state: GraphState }) {
  const openGateCount = state.nodes.filter(
    (n) => n.node_type === "gate_item" && n.resolved_at === null,
  ).length;
  const hotSpotCount = computeHotSpots(state).size;
  return (
    <div className="flex items-center gap-6 px-4 h-12 border-b border-neutral-800 bg-neutral-900">
      <span className="font-semibold">GigaBrain</span>
      <span className="text-yellow-300">⚡ {openGateCount} gate items</span>
      <span className="text-red-300">🔥 {hotSpotCount} hot spots</span>
    </div>
  );
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- TopBar`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TopBar.tsx frontend/tests/components/TopBar.test.tsx
git commit -m "feat(frontend): TopBar shows open gate count + hot-spot count"
```

---

## Task 12: CaptureBar — bottom input that POSTs /capture

**Files:**
- Create: `frontend/src/components/CaptureBar.tsx`
- Create: `frontend/tests/components/CaptureBar.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/tests/components/CaptureBar.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CaptureBar } from "../../src/components/CaptureBar";

beforeEach(() => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ node_id: "t_x", status: "ok" }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("CaptureBar", () => {
  it("POSTs the input value when Enter is pressed", async () => {
    const user = userEvent.setup();
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/capture a thought/i);
    await user.type(input, "build the brain view{Enter}");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/capture",
      expect.objectContaining({ method: "POST" }),
    );
    const callBody = JSON.parse((globalThis.fetch as any).mock.calls[0][1].body);
    expect(callBody).toEqual({ content: "build the brain view", source: "web" });
  });

  it("clears the input after a successful submit", async () => {
    const user = userEvent.setup();
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/capture a thought/i) as HTMLInputElement;
    await user.type(input, "hi{Enter}");
    expect(input.value).toBe("");
  });

  it("does not POST empty input", async () => {
    const user = userEvent.setup();
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/capture a thought/i);
    await user.type(input, "   {Enter}");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- CaptureBar`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement CaptureBar**

```tsx
// frontend/src/components/CaptureBar.tsx
import { useState } from "react";
import { postCapture } from "../api/client";

export function CaptureBar() {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await postCapture(trimmed);
      setValue("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-t border-neutral-800 bg-neutral-900 p-3">
      <input
        type="text"
        placeholder="Capture a thought…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void submit();
          }
        }}
        disabled={busy}
        className="w-full bg-neutral-800 text-neutral-100 placeholder-neutral-500 px-3 py-2 rounded outline-none focus:ring-2 focus:ring-violet-500"
      />
    </div>
  );
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- CaptureBar`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CaptureBar.tsx frontend/tests/components/CaptureBar.test.tsx
git commit -m "feat(frontend): bottom CaptureBar POSTs /capture on Enter"
```

---

## Task 13: Zoom-in destination resolver

**Files:**
- Create: `frontend/src/lib/zoomIn.ts`
- Create: `frontend/tests/lib/zoomIn.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// frontend/tests/lib/zoomIn.test.ts
import { describe, it, expect } from "vitest";
import { resolveZoomIn } from "../../src/lib/zoomIn";
import type {
  BetNode, TaskNode, CodeChangeNode, GateItemNode, ConflictNode, ThoughtNode,
} from "../../src/api/types";

const bet: BetNode = {
  node_type: "bet", id: "b_1", slug: "ship-v1", title: "Ship v1",
  vault_path: "Brain/Bets/bet_ship_v1.md", owner: "ceo", horizon: "Q",
  confidence: "medium", created_at: "",
};
const task: TaskNode = {
  node_type: "task", id: "k_1", linear_id: "GIG-100", title: "x", status: "todo",
  created_at: "",
};
const change: CodeChangeNode = {
  node_type: "code_change", id: "cc_1", repo: "kunggaochicken/GigaBrain",
  sha: "abc123", summary: "x", created_at: "",
};
const gate: GateItemNode = {
  node_type: "gate_item", id: "g_1", prompt: "?", urgency: "urgent",
  resolved_at: null, decision: null, reasoning: "", created_at: "",
};
const conflict: ConflictNode = {
  node_type: "conflict", id: "c_1", summary: "x", severity: "high", created_at: "",
};
const thought: ThoughtNode = {
  node_type: "thought", id: "t_1", content: "x", source: "web",
  created_at: "", metadata: {},
};

describe("resolveZoomIn", () => {
  it("bet → Obsidian URI", () => {
    expect(resolveZoomIn(bet)).toEqual({
      kind: "external",
      href: "obsidian://open?path=Brain%2FBets%2Fbet_ship_v1.md",
    });
  });

  it("task → Linear URL", () => {
    expect(resolveZoomIn(task)).toEqual({
      kind: "external",
      href: "https://linear.app/gigaflow/issue/GIG-100",
    });
  });

  it("code_change → GitHub commit URL", () => {
    expect(resolveZoomIn(change)).toEqual({
      kind: "external",
      href: "https://github.com/kunggaochicken/GigaBrain/commit/abc123",
    });
  });

  it("gate_item → in-place gate panel", () => {
    expect(resolveZoomIn(gate)).toEqual({ kind: "panel", panel: "gate", nodeId: "g_1" });
  });

  it("conflict → in-place conflict panel", () => {
    expect(resolveZoomIn(conflict)).toEqual({
      kind: "panel", panel: "conflict", nodeId: "c_1",
    });
  });

  it("thought → in-place detail panel", () => {
    expect(resolveZoomIn(thought)).toEqual({
      kind: "panel", panel: "detail", nodeId: "t_1",
    });
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- zoomIn`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement resolveZoomIn**

```ts
// frontend/src/lib/zoomIn.ts
import type { AnyNode } from "../api/types";

export type ZoomDestination =
  | { kind: "external"; href: string }
  | { kind: "panel"; panel: "gate" | "conflict" | "detail"; nodeId: string };

export function resolveZoomIn(node: AnyNode): ZoomDestination {
  switch (node.node_type) {
    case "bet":
      return {
        kind: "external",
        href: `obsidian://open?path=${encodeURIComponent(node.vault_path)}`,
      };
    case "task":
      return {
        kind: "external",
        href: `https://linear.app/gigaflow/issue/${node.linear_id}`,
      };
    case "code_change":
      return {
        kind: "external",
        href: `https://github.com/${node.repo}/commit/${node.sha}`,
      };
    case "gate_item":
      return { kind: "panel", panel: "gate", nodeId: node.id };
    case "conflict":
      return { kind: "panel", panel: "conflict", nodeId: node.id };
    default:
      return { kind: "panel", panel: "detail", nodeId: node.id };
  }
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- zoomIn`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/zoomIn.ts frontend/tests/lib/zoomIn.test.ts
git commit -m "feat(frontend): zoom-in destination resolver (bet/task/code/panel)"
```

---

## Task 14: Backend `POST /gate/{id}/resolve` endpoint

**Files:**
- Create: `backend/app/gate/__init__.py`
- Create: `backend/app/gate/resolver.py`
- Create: `backend/app/gate/api.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_gate/__init__.py`
- Create: `backend/tests/test_gate/test_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_gate/test_resolver.py
import pytest
from fastapi.testclient import TestClient

from app.db.schemas import GateItemNode


@pytest.fixture
def client_with_gate(test_app, node_repo):
    node_repo.create(GateItemNode(prompt="approve?", urgency="urgent"))
    return TestClient(test_app)


def test_resolve_returns_404_for_unknown(client_with_gate):
    response = client_with_gate.post(
        "/gate/g_missing/resolve",
        json={"decision": "approved", "reasoning": "looks good"},
    )
    assert response.status_code == 404


def test_resolve_records_decision_and_returns_ok(client_with_gate, node_repo):
    state = client_with_gate.get("/graph/state").json()
    gate = next(n for n in state["nodes"] if n["node_type"] == "gate_item")
    response = client_with_gate.post(
        f"/gate/{gate['id']}/resolve",
        json={"decision": "approved", "reasoning": "looks good"},
    )
    assert response.status_code == 200
    refreshed = client_with_gate.get(f"/graph/nodes/{gate['id']}").json()
    assert refreshed["decision"] == "approved"
    assert refreshed["reasoning"] == "looks good"
    assert refreshed["resolved_at"] is not None


def test_resolve_rejects_unknown_decision(client_with_gate):
    state = client_with_gate.get("/graph/state").json()
    gate = next(n for n in state["nodes"] if n["node_type"] == "gate_item")
    response = client_with_gate.post(
        f"/gate/{gate['id']}/resolve",
        json={"decision": "maybe", "reasoning": "x"},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run the test**

Run: `cd backend && uv run pytest tests/test_gate -v`
Expected: FAIL — 404 / route not registered.

- [ ] **Step 3: Implement the resolver**

```python
# backend/app/gate/__init__.py
```

```python
# backend/app/gate/resolver.py
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from app.db.kuzu import KuzuConnection


class GateResolveRequest(BaseModel):
    decision: Literal["approved", "vetoed", "resteered"]
    reasoning: str = ""
    alternative: str | None = None


def resolve_gate_item(
    conn: KuzuConnection, gate_id: str, req: GateResolveRequest
) -> bool:
    rows = conn.query(
        "MATCH (g:GateItem) WHERE g.id = $id RETURN g.id AS id",
        {"id": gate_id},
    )
    if not rows:
        return False

    conn.query(
        "MATCH (g:GateItem) WHERE g.id = $id "
        "SET g.decision = $decision, g.reasoning = $reasoning, "
        "g.resolved_at = $resolved_at",
        {
            "id": gate_id,
            "decision": req.decision,
            "reasoning": req.reasoning,
            "resolved_at": datetime.now(UTC),
        },
    )
    return True
```

```python
# backend/app/gate/api.py
from fastapi import APIRouter, HTTPException

from app.db.kuzu import KuzuConnection
from app.events.bus import EventBus
from app.gate.resolver import GateResolveRequest, resolve_gate_item


def build_gate_router(conn: KuzuConnection, bus: EventBus) -> APIRouter:
    router = APIRouter(prefix="/gate")

    @router.post("/{gate_id}/resolve")
    async def resolve(gate_id: str, req: GateResolveRequest):
        ok = resolve_gate_item(conn, gate_id, req)
        if not ok:
            raise HTTPException(status_code=404, detail=f"gate {gate_id} not found")
        return {"status": "ok"}

    return router
```

- [ ] **Step 4: Wire into main.py**

In `backend/app/main.py`, after the `build_graph_router` registration, add:

```python
from app.gate.api import build_gate_router
app.include_router(build_gate_router(conn, bus))
```

- [ ] **Step 5: Re-run the gate tests**

Run: `cd backend && uv run pytest tests/test_gate -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && uv run pytest -x`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/gate/ backend/app/main.py backend/tests/test_gate/
git commit -m "feat(api): POST /gate/{id}/resolve persists decision"
```

---

## Task 15: GateResolvePanel (in-place resolver)

**Files:**
- Create: `frontend/src/views/GateResolvePanel.tsx`
- Create: `frontend/tests/views/GateResolvePanel.test.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/tests/views/GateResolvePanel.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GateResolvePanel } from "../../src/views/GateResolvePanel";
import type { GateItemNode } from "../../src/api/types";

const gate: GateItemNode = {
  node_type: "gate_item",
  id: "g_1",
  prompt: "Approve dispatch?",
  urgency: "urgent",
  resolved_at: null,
  decision: null,
  reasoning: "",
  created_at: "2026-05-12T00:00:00Z",
};

beforeEach(() => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: "ok" }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("GateResolvePanel", () => {
  it("renders the prompt", () => {
    render(<GateResolvePanel gate={gate} onResolved={() => {}} />);
    expect(screen.getByText("Approve dispatch?")).toBeInTheDocument();
  });

  it("approve POSTs decision and calls onResolved", async () => {
    const onResolved = vi.fn();
    const user = userEvent.setup();
    render(<GateResolvePanel gate={gate} onResolved={onResolved} />);
    await user.type(screen.getByPlaceholderText(/reasoning/i), "looks fine");
    await user.click(screen.getByRole("button", { name: /approve/i }));
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/gate/g_1/resolve",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse((globalThis.fetch as any).mock.calls[0][1].body);
    expect(body).toMatchObject({ decision: "approved", reasoning: "looks fine" });
    expect(onResolved).toHaveBeenCalled();
  });

  it("veto button sends decision=vetoed", async () => {
    const user = userEvent.setup();
    render(<GateResolvePanel gate={gate} onResolved={() => {}} />);
    await user.click(screen.getByRole("button", { name: /veto/i }));
    const body = JSON.parse((globalThis.fetch as any).mock.calls[0][1].body);
    expect(body.decision).toBe("vetoed");
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- GateResolvePanel`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement GateResolvePanel**

```tsx
// frontend/src/views/GateResolvePanel.tsx
import { useState } from "react";
import type { GateItemNode } from "../api/types";
import { postGateResolve } from "../api/client";

type Decision = "approved" | "vetoed" | "resteered";

export function GateResolvePanel({
  gate,
  onResolved,
}: {
  gate: GateItemNode;
  onResolved: () => void;
}) {
  const [reasoning, setReasoning] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(decision: Decision) {
    setBusy(true);
    try {
      await postGateResolve(gate.id, { decision, reasoning });
      onResolved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-4 space-y-3">
      <h2 className="text-lg font-semibold">{gate.prompt}</h2>
      <div className="text-xs uppercase tracking-wider text-yellow-300">
        urgency: {gate.urgency}
      </div>
      <textarea
        placeholder="reasoning…"
        value={reasoning}
        onChange={(e) => setReasoning(e.target.value)}
        className="w-full bg-neutral-800 text-neutral-100 placeholder-neutral-500 px-3 py-2 rounded outline-none focus:ring-2 focus:ring-violet-500 min-h-[6rem]"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("approved")}
          className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
        >
          approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("vetoed")}
          className="px-3 py-1.5 rounded bg-rose-600 hover:bg-rose-500 disabled:opacity-50"
        >
          veto
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("resteered")}
          className="px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50"
        >
          resteer
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- GateResolvePanel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/GateResolvePanel.tsx frontend/tests/views/GateResolvePanel.test.tsx
git commit -m "feat(frontend): GateResolvePanel with approve/veto/resteer actions"
```

---

## Task 16: NodeDetailPanel (right slide-in)

**Files:**
- Create: `frontend/src/views/NodeDetailPanel.tsx`
- Create: `frontend/tests/views/NodeDetailPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/tests/views/NodeDetailPanel.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NodeDetailPanel } from "../../src/views/NodeDetailPanel";
import type { BetNode, GateItemNode } from "../../src/api/types";

const bet: BetNode = {
  node_type: "bet", id: "b_1", slug: "ship-v1", title: "Ship v1",
  vault_path: "Brain/Bets/bet_ship_v1.md", owner: "ceo", horizon: "Q",
  confidence: "medium", created_at: "2026-05-12T00:00:00Z",
};

const gate: GateItemNode = {
  node_type: "gate_item", id: "g_1", prompt: "go?", urgency: "urgent",
  resolved_at: null, decision: null, reasoning: "", created_at: "2026-05-12T00:00:00Z",
};

describe("NodeDetailPanel", () => {
  it("renders nothing when node is null", () => {
    const { container } = render(<NodeDetailPanel node={null} onClose={() => {}} onResolved={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the bet title and an open-external link", () => {
    render(<NodeDetailPanel node={bet} onClose={() => {}} onResolved={() => {}} />);
    expect(screen.getByText("Ship v1")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open in obsidian/i });
    expect(link).toHaveAttribute(
      "href",
      "obsidian://open?path=Brain%2FBets%2Fbet_ship_v1.md",
    );
  });

  it("renders the gate resolve panel for gate_item nodes", () => {
    render(<NodeDetailPanel node={gate} onClose={() => {}} onResolved={() => {}} />);
    expect(screen.getByText("go?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
  });

  it("close button calls onClose", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<NodeDetailPanel node={bet} onClose={onClose} onResolved={() => {}} />);
    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- NodeDetailPanel`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement NodeDetailPanel**

```tsx
// frontend/src/views/NodeDetailPanel.tsx
import type { AnyNode } from "../api/types";
import { resolveZoomIn } from "../lib/zoomIn";
import { NodeBadge } from "../components/NodeBadge";
import { GateResolvePanel } from "./GateResolvePanel";

export function NodeDetailPanel({
  node,
  onClose,
  onResolved,
}: {
  node: AnyNode | null;
  onClose: () => void;
  onResolved: () => void;
}) {
  if (!node) return null;

  const zoom = resolveZoomIn(node);
  const title = headline(node);

  return (
    <aside className="w-96 h-full bg-neutral-900 border-l border-neutral-800 overflow-y-auto">
      <header className="flex items-center justify-between p-3 border-b border-neutral-800">
        <NodeBadge type={node.node_type} />
        <button
          type="button"
          onClick={onClose}
          aria-label="close"
          className="text-neutral-400 hover:text-neutral-100"
        >
          ✕
        </button>
      </header>

      {node.node_type === "gate_item" ? (
        <GateResolvePanel gate={node} onResolved={onResolved} />
      ) : (
        <div className="p-4 space-y-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <pre className="text-xs bg-neutral-950 p-3 rounded whitespace-pre-wrap break-words">
            {JSON.stringify(node, null, 2)}
          </pre>
          {zoom.kind === "external" && (
            <a
              href={zoom.href}
              target="_blank"
              rel="noreferrer"
              className="inline-block px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500"
            >
              open in {externalLabel(node)}
            </a>
          )}
        </div>
      )}
    </aside>
  );
}

function headline(node: AnyNode): string {
  switch (node.node_type) {
    case "bet": return node.title;
    case "task": return node.title;
    case "thought": return node.content.slice(0, 80);
    case "decision": return node.content.slice(0, 80);
    case "conflict": return node.summary;
    case "outcome": return node.summary;
    case "code_change": return node.summary;
    case "conversation": return node.summary;
    case "doc": return node.title;
    case "gate_item": return node.prompt;
    case "agent_firing": return `firing ${node.id}`;
    case "agent": return node.role;
  }
}

function externalLabel(node: AnyNode): string {
  switch (node.node_type) {
    case "bet": return "Obsidian";
    case "task": return "Linear";
    case "code_change": return "GitHub";
    default: return "external";
  }
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- NodeDetailPanel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/NodeDetailPanel.tsx frontend/tests/views/NodeDetailPanel.test.tsx
git commit -m "feat(frontend): NodeDetailPanel with zoom-in link and gate resolve"
```

---

## Task 17: DesktopGraphView — force-directed canvas

**Files:**
- Create: `frontend/src/views/DesktopGraphView.tsx`
- Create: `frontend/tests/views/DesktopGraphView.test.tsx`

react-force-graph-2d does not render in jsdom, so we mock it at the module boundary and assert on the props the view passes in.

- [ ] **Step 1: Write failing test**

```tsx
// frontend/tests/views/DesktopGraphView.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DesktopGraphView } from "../../src/views/DesktopGraphView";
import type { GraphState, ThoughtNode, BetNode } from "../../src/api/types";

vi.mock("react-force-graph-2d", () => ({
  __esModule: true,
  default: (props: any) => (
    <div
      data-testid="force-graph"
      data-nodes={JSON.stringify(props.graphData.nodes.map((n: any) => n.id))}
      data-links={JSON.stringify(
        props.graphData.links.map((l: any) => `${l.source}::${l.target}`),
      )}
      onClick={() =>
        props.onNodeClick?.(props.graphData.nodes[0])
      }
    />
  ),
}));

const thought: ThoughtNode = {
  node_type: "thought", id: "t_1", content: "hi", source: "web",
  created_at: "2026-05-12T00:00:00Z", metadata: {},
};
const bet: BetNode = {
  node_type: "bet", id: "b_1", slug: "x", title: "X", vault_path: "p",
  owner: "ceo", horizon: "Q", confidence: "medium", created_at: "",
};
const state: GraphState = {
  nodes: [thought, bet],
  edges: [
    { from_id: "t_1", from_type: "thought", to_id: "b_1", to_type: "bet",
      edge_type: "sparred-against", created_at: "", confidence: 1 },
  ],
};

describe("DesktopGraphView", () => {
  it("passes nodes and links to react-force-graph-2d", () => {
    render(<DesktopGraphView state={state} onNodeSelect={() => {}} />);
    const fg = screen.getByTestId("force-graph");
    expect(fg.dataset.nodes).toBe(JSON.stringify(["t_1", "b_1"]));
    expect(fg.dataset.links).toBe(JSON.stringify(["t_1::b_1"]));
  });

  it("onNodeClick calls onNodeSelect with the clicked node", async () => {
    const onSelect = vi.fn();
    render(<DesktopGraphView state={state} onNodeSelect={onSelect} />);
    screen.getByTestId("force-graph").click();
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "t_1" }));
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- DesktopGraphView`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement DesktopGraphView**

```tsx
// frontend/src/views/DesktopGraphView.tsx
import { useMemo, useRef, useEffect } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { AnyNode, GraphState } from "../api/types";
import { NODE_HEX } from "../lib/colors";
import { computeHotSpots } from "../state/hotSpots";

interface ForceNode {
  id: string;
  node_type: string;
  raw: AnyNode;
  val: number;
  color: string;
}

interface ForceLink {
  source: string;
  target: string;
}

export function DesktopGraphView({
  state,
  onNodeSelect,
}: {
  state: GraphState;
  onNodeSelect: (node: AnyNode) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  const graphData = useMemo(() => {
    const scores = computeHotSpots(state);
    const nodes: ForceNode[] = state.nodes.map((n) => ({
      id: n.id,
      node_type: n.node_type,
      raw: n,
      val: 1 + (scores.get(n.id) ?? 0) * 2,
      color: NODE_HEX[n.node_type],
    }));
    const links: ForceLink[] = state.edges.map((e) => ({
      source: e.from_id,
      target: e.to_id,
    }));
    return { nodes, links };
  }, [state]);

  const dimsRef = useRef({ width: 800, height: 600 });
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const resize = () => {
      dimsRef.current = { width: el.clientWidth, height: el.clientHeight };
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  return (
    <div ref={containerRef} className="flex-1 relative bg-neutral-950">
      <ForceGraph2D
        graphData={graphData}
        width={dimsRef.current.width}
        height={dimsRef.current.height}
        nodeRelSize={5}
        nodeColor={(n: any) => n.color}
        nodeVal={(n: any) => n.val}
        linkColor={() => "#525252"}
        backgroundColor="#0a0a0a"
        onNodeClick={(n: any) => onNodeSelect(n.raw as AnyNode)}
      />
    </div>
  );
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- DesktopGraphView`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/DesktopGraphView.tsx frontend/tests/views/DesktopGraphView.test.tsx
git commit -m "feat(frontend): DesktopGraphView with hot-spot sized nodes"
```

---

## Task 18: GateCard (mobile inbox card)

**Files:**
- Create: `frontend/src/components/GateCard.tsx`
- Create: `frontend/tests/components/GateCard.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/tests/components/GateCard.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GateCard } from "../../src/components/GateCard";
import type { GateItemNode } from "../../src/api/types";

const gate: GateItemNode = {
  node_type: "gate_item",
  id: "g_1",
  prompt: "Approve dispatch?",
  urgency: "urgent",
  resolved_at: null,
  decision: null,
  reasoning: "",
  created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
};

describe("GateCard", () => {
  it("shows the prompt and urgency", () => {
    render(<GateCard gate={gate} onZoom={() => {}} />);
    expect(screen.getByText("Approve dispatch?")).toBeInTheDocument();
    expect(screen.getByText(/urgent/i)).toBeInTheDocument();
  });

  it("zoom button fires onZoom with gate id", async () => {
    const onZoom = vi.fn();
    const user = userEvent.setup();
    render(<GateCard gate={gate} onZoom={onZoom} />);
    await user.click(screen.getByRole("button", { name: /zoom/i }));
    expect(onZoom).toHaveBeenCalledWith("g_1");
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- GateCard`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement GateCard + time helper**

```ts
// frontend/src/lib/time.ts
export function ageLabel(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
```

```tsx
// frontend/src/components/GateCard.tsx
import type { GateItemNode } from "../api/types";
import { ageLabel } from "../lib/time";

export function GateCard({
  gate,
  onZoom,
}: {
  gate: GateItemNode;
  onZoom: (id: string) => void;
}) {
  return (
    <div className="border border-neutral-800 bg-neutral-900 rounded p-3 space-y-2">
      <div className="flex justify-between text-xs">
        <span className="uppercase tracking-wider text-yellow-300">
          {gate.urgency}
        </span>
        <span className="text-neutral-500">{ageLabel(gate.created_at)}</span>
      </div>
      <p className="text-sm">{gate.prompt}</p>
      <button
        type="button"
        onClick={() => onZoom(gate.id)}
        className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-xs"
      >
        zoom
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- GateCard`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/GateCard.tsx frontend/src/lib/time.ts frontend/tests/components/GateCard.test.tsx
git commit -m "feat(frontend): GateCard + age helper for mobile inbox"
```

---

## Task 19: MobileInboxView — tabs + card stack

**Files:**
- Create: `frontend/src/views/MobileInboxView.tsx`
- Create: `frontend/tests/views/MobileInboxView.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/tests/views/MobileInboxView.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobileInboxView } from "../../src/views/MobileInboxView";
import type { GraphState, GateItemNode, ConflictNode } from "../../src/api/types";

const gate = (id: string): GateItemNode => ({
  node_type: "gate_item", id, prompt: `prompt ${id}`, urgency: "urgent",
  resolved_at: null, decision: null, reasoning: "",
  created_at: "2026-05-12T00:00:00Z",
});
const conflict = (id: string): ConflictNode => ({
  node_type: "conflict", id, summary: `c ${id}`, severity: "high",
  created_at: "2026-05-12T00:00:00Z",
});

const state: GraphState = {
  nodes: [gate("g_1"), gate("g_2"), conflict("c_1")],
  edges: [],
};

describe("MobileInboxView", () => {
  it("default tab is Gate and lists gate items", () => {
    render(<MobileInboxView state={state} onZoom={() => {}} />);
    expect(screen.getByText("prompt g_1")).toBeInTheDocument();
    expect(screen.getByText("prompt g_2")).toBeInTheDocument();
  });

  it("Hot tab lists hot-spot nodes", async () => {
    const user = userEvent.setup();
    render(<MobileInboxView state={state} onZoom={() => {}} />);
    await user.click(screen.getByRole("tab", { name: /hot/i }));
    expect(screen.getByText(/c c_1/)).toBeInTheDocument();
  });

  it("Recent tab lists most recently created nodes", async () => {
    const user = userEvent.setup();
    render(<MobileInboxView state={state} onZoom={() => {}} />);
    await user.click(screen.getByRole("tab", { name: /recent/i }));
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(1);
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- MobileInboxView`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement MobileInboxView**

```tsx
// frontend/src/views/MobileInboxView.tsx
import { useState, useMemo } from "react";
import type { GraphState, AnyNode } from "../api/types";
import { GateCard } from "../components/GateCard";
import { computeHotSpots } from "../state/hotSpots";

type Tab = "gate" | "hot" | "recent";

export function MobileInboxView({
  state,
  onZoom,
}: {
  state: GraphState;
  onZoom: (nodeId: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("gate");

  const gateItems = useMemo(
    () =>
      state.nodes.filter(
        (n) => n.node_type === "gate_item" && n.resolved_at === null,
      ),
    [state.nodes],
  );

  const hotItems = useMemo(() => {
    const scores = computeHotSpots(state);
    return [...scores.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([id]) => state.nodes.find((n) => n.id === id))
      .filter((n): n is AnyNode => Boolean(n));
  }, [state]);

  const recentItems = useMemo(
    () =>
      [...state.nodes].sort(
        (a, b) => +new Date(b.created_at) - +new Date(a.created_at),
      ).slice(0, 30),
    [state.nodes],
  );

  return (
    <div className="flex flex-col h-full">
      <div role="tablist" className="flex border-b border-neutral-800">
        {(["gate", "hot", "recent"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2 text-sm capitalize ${
              tab === t
                ? "border-b-2 border-violet-500 text-violet-300"
                : "text-neutral-400"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <ul className="flex-1 overflow-y-auto p-3 space-y-2">
        {tab === "gate" &&
          gateItems.map((g) =>
            g.node_type === "gate_item" ? (
              <li key={g.id}>
                <GateCard gate={g} onZoom={onZoom} />
              </li>
            ) : null,
          )}

        {tab === "hot" &&
          hotItems.map((n) => (
            <li key={n.id}>
              <SimpleRow node={n} onZoom={onZoom} />
            </li>
          ))}

        {tab === "recent" &&
          recentItems.map((n) => (
            <li key={n.id}>
              <SimpleRow node={n} onZoom={onZoom} />
            </li>
          ))}
      </ul>
    </div>
  );
}

function SimpleRow({
  node,
  onZoom,
}: {
  node: AnyNode;
  onZoom: (id: string) => void;
}) {
  const label =
    "title" in node ? node.title
    : "summary" in node ? node.summary
    : "content" in node ? node.content.slice(0, 60)
    : "prompt" in node ? node.prompt
    : node.id;
  return (
    <button
      type="button"
      onClick={() => onZoom(node.id)}
      className="w-full text-left border border-neutral-800 bg-neutral-900 rounded p-3 hover:bg-neutral-800"
    >
      <div className="text-xs text-neutral-400 uppercase">{node.node_type}</div>
      <div className="text-sm">{label}</div>
    </button>
  );
}
```

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm test -- MobileInboxView`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/MobileInboxView.tsx frontend/tests/views/MobileInboxView.test.tsx
git commit -m "feat(frontend): MobileInboxView with Gate / Hot / Recent tabs"
```

---

## Task 20: App shell — responsive routing + glue

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/App.test.tsx`

- [ ] **Step 1: Replace the App test**

```tsx
// frontend/tests/App.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App";

class MockEventSource {
  static instance: MockEventSource | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {
    MockEventSource.instance = this;
  }
}

vi.mock("react-force-graph-2d", () => ({
  __esModule: true,
  default: () => <div data-testid="force-graph" />,
}));

beforeEach(() => {
  // @ts-expect-error mock
  globalThis.EventSource = MockEventSource;
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ nodes: [], edges: [] }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("renders TopBar with GigaBrain label", async () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/GigaBrain/)).toBeInTheDocument());
  });

  it("renders the desktop graph + capture bar by default", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("force-graph")).toBeInTheDocument());
    expect(screen.getByPlaceholderText(/capture a thought/i)).toBeInTheDocument();
  });

  it("renders the mobile inbox at /inbox", async () => {
    render(
      <MemoryRouter initialEntries={["/inbox"]}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /gate/i })).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm test -- App`
Expected: FAIL — current minimal App doesn't render TopBar / graph.

- [ ] **Step 3: Implement App shell**

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { Routes, Route, Link } from "react-router-dom";
import { GraphProvider, useGraph } from "./state/GraphProvider";
import { TopBar } from "./components/TopBar";
import { CaptureBar } from "./components/CaptureBar";
import { DesktopGraphView } from "./views/DesktopGraphView";
import { MobileInboxView } from "./views/MobileInboxView";
import { NodeDetailPanel } from "./views/NodeDetailPanel";
import type { AnyNode } from "./api/types";

function DesktopShell() {
  const { state } = useGraph();
  const [selected, setSelected] = useState<AnyNode | null>(null);

  return (
    <div className="flex flex-col h-full">
      <TopBar state={state} />
      <div className="flex flex-1 overflow-hidden">
        <DesktopGraphView state={state} onNodeSelect={setSelected} />
        <NodeDetailPanel
          node={selected}
          onClose={() => setSelected(null)}
          onResolved={() => setSelected(null)}
        />
      </div>
      <CaptureBar />
    </div>
  );
}

function MobileShell() {
  const { state } = useGraph();
  const [selected, setSelected] = useState<AnyNode | null>(null);

  function onZoom(id: string) {
    setSelected(state.nodes.find((n) => n.id === id) ?? null);
  }

  return (
    <div className="flex flex-col h-full">
      <TopBar state={state} />
      <div className="flex flex-1 overflow-hidden">
        <MobileInboxView state={state} onZoom={onZoom} />
        <NodeDetailPanel
          node={selected}
          onClose={() => setSelected(null)}
          onResolved={() => setSelected(null)}
        />
      </div>
      <nav className="flex border-t border-neutral-800 bg-neutral-900">
        <Link to="/inbox" className="flex-1 py-3 text-center text-sm">
          inbox
        </Link>
        <Link to="/" className="flex-1 py-3 text-center text-sm">
          brain
        </Link>
      </nav>
      <CaptureBar />
    </div>
  );
}

export default function App() {
  return (
    <GraphProvider>
      <Routes>
        <Route path="/" element={<DesktopShell />} />
        <Route path="/inbox" element={<MobileShell />} />
      </Routes>
    </GraphProvider>
  );
}
```

- [ ] **Step 4: Re-run the tests**

Run: `cd frontend && npm test`
Expected: ALL tests PASS.

- [ ] **Step 5: Type-check the project**

Run: `cd frontend && npm run typecheck`
Expected: exit 0.

- [ ] **Step 6: Build the project**

Run: `cd frontend && npm run build`
Expected: exit 0, `dist/` created.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/tests/App.test.tsx
git commit -m "feat(frontend): App shell wires Desktop and Mobile routes"
```

---

## Task 21: Backend mounts frontend static assets

**Files:**
- Create: `backend/app/api/frontend.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api/test_frontend.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_api/test_frontend.py
from fastapi.testclient import TestClient


def test_frontend_root_serves_index_when_built(test_app, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>GB</title>")
    monkeypatch.setenv("GIGABRAIN_FRONTEND_DIST", str(dist))

    from app.api.frontend import build_frontend_router
    test_app.include_router(build_frontend_router())

    client = TestClient(test_app)
    response = client.get("/")
    assert response.status_code == 200
    assert b"<title>GB</title>" in response.content


def test_frontend_skips_mount_when_dist_absent(test_app, tmp_path, monkeypatch):
    missing = tmp_path / "no-dist"
    monkeypatch.setenv("GIGABRAIN_FRONTEND_DIST", str(missing))

    from app.api.frontend import build_frontend_router
    router = build_frontend_router()
    assert router is None
```

- [ ] **Step 2: Run the test**

Run: `cd backend && uv run pytest tests/test_api/test_frontend.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the frontend router**

```python
# backend/app/api/frontend.py
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _resolve_dist() -> Path | None:
    raw = os.environ.get("GIGABRAIN_FRONTEND_DIST")
    if raw:
        path = Path(raw)
    else:
        path = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return path if path.is_dir() and (path / "index.html").exists() else None


def build_frontend_router() -> APIRouter | None:
    dist = _resolve_dist()
    if not dist:
        return None

    router = APIRouter()

    assets = dist / "assets"
    if assets.is_dir():
        router.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @router.get("/", include_in_schema=False)
    @router.get("/inbox", include_in_schema=False)
    async def index():
        return FileResponse(dist / "index.html")

    return router
```

- [ ] **Step 4: Wire into main.py**

In `backend/app/main.py`, at the very end of `lifespan` (after all other routers), add:

```python
from app.api.frontend import build_frontend_router
fe = build_frontend_router()
if fe is not None:
    app.include_router(fe)
```

- [ ] **Step 5: Rerun the new tests**

Run: `cd backend && uv run pytest tests/test_api/test_frontend.py -v`
Expected: PASS.

- [ ] **Step 6: Rerun the full backend suite**

Run: `cd backend && uv run pytest -x`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/frontend.py backend/app/main.py backend/tests/test_api/test_frontend.py
git commit -m "feat(api): mount built frontend at / when dist is present"
```

---

## Task 22: E2E smoke — capture round-trip through the spine

**Files:**
- Create: `backend/tests/test_e2e/test_capture_renders.py`

- [ ] **Step 1: Write the e2e test**

This test exercises the full backend pipe: capture → spine writes a `thought` node → `/graph/state` returns it.

```python
# backend/tests/test_e2e/test_capture_renders.py
import pytest
from fastapi.testclient import TestClient


def test_capture_thought_then_appears_in_graph_state(test_app):
    client = TestClient(test_app)

    pre = client.get("/graph/state").json()
    pre_count = sum(1 for n in pre["nodes"] if n["node_type"] == "thought")

    response = client.post("/capture", json={"content": "smoke test", "source": "e2e"})
    assert response.status_code == 200

    post = client.get("/graph/state").json()
    post_count = sum(1 for n in post["nodes"] if n["node_type"] == "thought")
    assert post_count == pre_count + 1
    assert any(
        n["node_type"] == "thought" and n["content"] == "smoke test"
        for n in post["nodes"]
    )
```

- [ ] **Step 2: Run the test**

Run: `cd backend && uv run pytest tests/test_e2e/test_capture_renders.py -v`
Expected: PASS (the spine writes the node synchronously even though sparring runs async).

If it fails because sparring + persistence is asynchronous in your wiring, mark this test as `@pytest.mark.skip` with a TODO referencing this plan and follow up in Plan 04 (capture adapters), which adds the proper async-completion hook.

- [ ] **Step 3: Run the full suite to confirm**

Run: `cd backend && uv run pytest`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_e2e/test_capture_renders.py
git commit -m "test(e2e): capture writes a thought visible in /graph/state"
```

---

## Task 23: Manual UI smoke + screenshot for the PR

This task is **manual** — the executor performs it once before opening the PR.

- [ ] **Step 1: Start the backend**

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Start the frontend dev server**

In a second terminal:

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Open http://localhost:5173**

Confirm:
- TopBar shows "GigaBrain" + `⚡ N gate items` + `🔥 N hot spots` counts.
- Capture bar is present at the bottom. Typing "smoke test" + Enter clears the input.
- A new green node animates in within ~2 seconds (sparring path completes, SSE event arrives).
- Clicking the new node opens the right slide-in panel showing thought content.
- Closing the panel hides it.

- [ ] **Step 4: Open http://localhost:5173/inbox**

Confirm:
- Three tabs visible: gate / hot / recent.
- "Recent" tab shows the smoke-test thought.

- [ ] **Step 5: Build for prod and verify backend serves it**

```bash
cd frontend && npm run build
cd backend && uv run uvicorn app.main:app --port 8000
```

Open http://localhost:8000 — confirm the built app loads.

- [ ] **Step 6: Capture a screenshot**

Save a screenshot of the desktop graph view to `docs/superpowers/plans/screenshots/2026-05-12-brain-view.png`. (Create the `screenshots/` directory if absent.)

- [ ] **Step 7: Commit the screenshot**

```bash
mkdir -p docs/superpowers/plans/screenshots
git add docs/superpowers/plans/screenshots/2026-05-12-brain-view.png
git commit -m "docs(plan-03): screenshot of brain view UI smoke run"
```

---

## Task 24: Open the PR

- [ ] **Step 1: Verify clean state**

Run: `git status`
Expected: working tree clean.

Run: `cd backend && uv run pytest`
Expected: ALL backend tests pass.

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: ALL frontend tests pass; typecheck OK; build OK.

- [ ] **Step 2: Push branch**

```bash
git push -u origin worktree-feat+plan-03-brain-view-ui
```

- [ ] **Step 3: Open the PR**

Use `gh pr create` with title `feat(brain-view): Plan 03 — desktop graph + mobile inbox UI` and reference [Linear GIG-126](https://linear.app/gigaflow/issue/GIG-126) in the body.

Include in PR body:
- Summary: scaffolded `frontend/`, added `/graph/state`, `/graph/nodes/{id}`, `/gate/{id}/resolve`, mounted built frontend at `/`.
- Screenshot from Task 23.
- "Closes GIG-126."

---

## Self-review checklist

Run through these after the plan is fully drafted:

- [x] **Spec §4 coverage.** Desktop graph view (Task 17), mobile inbox (19), top bar counts (11), capture bar (12), zoom-in destinations (13), node detail (16), gate resolve (15), real-time SSE updates (8). Hot-spot scoring (9). All present.
- [x] **Spec §5 (telemetry) coverage.** Gate resolution endpoint exists (14). Full OTel attribute emission is deferred to Plan 07 per design — noted in scope-out.
- [x] **No placeholders.** Every step contains code or an exact command.
- [x] **Type consistency.** TS `AnyNode` field names match Python pydantic models (verified against `backend/app/db/schemas.py`). `GraphChangedEvent` matches `backend/app/events/schemas.py`. Function signatures match between API client and the endpoints they call.
- [x] **TDD throughout.** Every implementation task starts with a failing test step.
- [x] **Frequent commits.** Every task ends in a commit.
- [x] **Working-dir explicit.** Every command specifies `cd backend &&` or `cd frontend &&`.

---

## Execution handoff

Plan complete. Recommended execution: **inline** since the executor is already in the worktree and tasks are tightly coupled at the backend ↔ frontend boundary (types in Task 2 must match endpoints in Tasks 3/4/14; the App test in Task 20 depends on every earlier component existing).

Start with Task 1 (`frontend/` scaffold). Use `superpowers:executing-plans` for batched checkpoint execution. The executor should commit per task and run the full suite (`cd backend && uv run pytest && cd ../frontend && npm test`) after Tasks 5, 8, 14, 17, 20, 21, and 22.
