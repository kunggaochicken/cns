# GigaBrain CNS v2 — Plan 2: Agent Runtime

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent runtime that subscribes to `fire.neuron` events emitted by the spine and actually does reversible-internal work (drafts code, writes vault files, runs tests, etc.). After this plan ships, a captured thought classified `clear + actionable` will trigger an agent that drafts work and records it in the graph as an `AgentFiring`, with full OTel instrumentation flowing to GigaFlow.

**Architecture:** A single `agent-worker` process subscribes to the in-process EventBus (already wired by the spine in `backend/app/main.py`'s lifespan). When `FireNeuron` events arrive, it dequeues for the matching agent, creates an `AgentFiring` node, runs a `pydantic-ai` Agent with a tool allowlist enforced both at the agent declaration AND a global "reversible-internal fence" middleware, and writes the agent's outputs back as graph nodes (CodeChange, Doc, etc.). Agents are first-class graph nodes loaded from `agents.yaml` at startup; the user can pause/resume/take over any agent's queue via `/agents/{id}/...` endpoints.

**Tech Stack:** Python 3.11+, `pydantic-ai>=1.0`, Anthropic SDK, OpenTelemetry GenAI auto-instrumentation, Click for the `gigabrain agents` CLI, FastAPI for the `/agents/*` HTTP endpoints. All on top of the spine's KuzuDB + EventBus.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-gigabrain-cns-v2-design.md`](../specs/2026-05-06-gigabrain-cns-v2-design.md) §3 (Agents & autonomy).

**Lessons from Plan 1 baked in:**
- pydantic-ai 1.x API: `output_type=` (not `result_type=`), `result.output` (not `.data`), `AnthropicModel(model, provider=AnthropicProvider(api_key=...))`
- `with TestClient(app) as client:` is required for FastAPI lifespan to fire
- Routes that need lifespan-built deps mount via `app.include_router(builder(...))` *inside* `lifespan()`
- Real-Kuzu integration tests catch DDL bugs that mock-only tests miss — write at least one per critical path
- `node_type` is a `Literal` discriminator field, not a `@property` — repositories `model_dump(exclude={"node_type"})` before insert
- AgentFiringNode uses `started_at` not `created_at` (already in `_EXTRA_EXCLUDE`)
- Default config paths must be writable without sudo (so `./data/...`, not `/var/log/...`)
- Shared SQLite/Kuzu connections need `threading.Lock` if accessed from multiple threads

---

## Prerequisite: align AgentNode schema with Kuzu DDL

The spine has a residual schema/DDL inconsistency for `AgentNode`. The pydantic schema declares `created_at` (inherited from `_BaseNode`) but the DDL has no such column. Plan 1's `NodeRepository._EXTRA_EXCLUDE` papers over it.

This plan needs to write Agents to the DB on startup, so the issue surfaces immediately. Task 1 below handles this cleanly by adjusting both sides.

---

## File structure

```
backend/
├── agents.yaml.example                # Default fleet config (committed; users copy to agents.yaml)
└── app/
    ├── agents/
    │   ├── __init__.py
    │   ├── config.py                  # Pydantic models for agents.yaml + loader
    │   ├── registry.py                # Sync yaml → graph nodes; CRUD on Agent rows
    │   ├── runtime.py                 # AgentRuntime = pydantic-ai Agent + tool fence
    │   ├── worker.py                  # Background worker subscribing to fire.neuron
    │   ├── prompts.py                 # System prompt template per role
    │   ├── tools/
    │   │   ├── __init__.py
    │   │   ├── base.py                # Tool ABC + fence enforcement decorator
    │   │   ├── vault_read.py          # Read from Obsidian vault (paths only — vault path comes from config)
    │   │   ├── vault_write.py         # Write to vault (drafts, notes)
    │   │   ├── run_tests.py           # Subprocess wrapper for project test command
    │   │   └── stage_commits.py       # git add + git commit (no push) in a configured repo
    │   └── api.py                     # /agents/* HTTP endpoints (builder factory pattern)
    └── cli/
        ├── __init__.py
        └── agents.py                  # `gigabrain agents` command (list)

tests/
├── test_agents/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_registry.py
│   ├── test_runtime.py
│   ├── test_worker.py
│   ├── test_prompts.py
│   ├── test_tools/
│   │   ├── __init__.py
│   │   ├── test_base.py
│   │   ├── test_vault_read.py
│   │   ├── test_vault_write.py
│   │   ├── test_run_tests.py
│   │   └── test_stage_commits.py
│   ├── test_api.py
│   └── test_e2e_fire_neuron.py
└── test_cli/
    ├── __init__.py
    └── test_agents.py
```

---

## Task 1: Reconcile AgentNode schema and Kuzu DDL

**Files:**
- Modify: `backend/app/db/schemas.py` (drop `created_at` from AgentNode)
- Modify: `backend/kuzu_schema/001_nodes.cypher` (add `created_at`, `enabled` to Agent)
- Modify: `backend/app/db/nodes.py` (remove AgentNode from `_EXTRA_EXCLUDE`)
- Modify: `backend/tests/test_db/test_nodes.py` (add round-trip test for AgentNode now that fields align)

**Decision:** add `created_at TIMESTAMP` and `enabled BOOL` to the `Agent` Kuzu DDL, override `created_at` field in `AgentNode` (already present from `_BaseNode`, just remove the override-skip). This eliminates the remap dict for `AgentNode` and adds an `enabled` flag we'll need to disable agents without removing them from the graph.

- [ ] **Step 1: Write failing test for AgentNode round-trip**

```python
# Add to backend/tests/test_db/test_nodes.py
def test_create_and_get_agent(conn: KuzuConnection):
    from app.db.schemas import AgentNode
    repo = NodeRepository(conn)
    agent = AgentNode(
        id="engineer-1",
        role="engineer",
        persona="Drafts code, runs tests.",
        state="idle",
        enabled=True,
    )
    repo.create(agent)
    fetched = repo.get(agent.id, "Agent")
    assert fetched["id"] == "engineer-1"
    assert fetched["role"] == "engineer"
    assert fetched["enabled"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_db/test_nodes.py::test_create_and_get_agent -v`
Expected: FAIL — `enabled` field doesn't exist on AgentNode.

- [ ] **Step 3: Update DDL**

Edit `backend/kuzu_schema/001_nodes.cypher` — replace the existing `Agent` table definition with:

```cypher
CREATE NODE TABLE IF NOT EXISTS Agent(
  id STRING, role STRING, persona STRING, state STRING,
  current_firing STRING, last_active TIMESTAMP,
  created_at TIMESTAMP, enabled BOOL,
  PRIMARY KEY (id)
);
```

- [ ] **Step 4: Update pydantic schema**

In `backend/app/db/schemas.py`, replace `AgentNode` with:

```python
class AgentNode(_BaseNode):
    node_type: Literal[NodeType.AGENT] = NodeType.AGENT
    # No id default_factory: agents have stable, externally-configured IDs (from agents.yaml)
    id: str
    role: str
    persona: str
    state: str = "idle"
    current_firing: str | None = None
    last_active: datetime | None = None
    enabled: bool = True
```

- [ ] **Step 5: Remove AgentNode from `_EXTRA_EXCLUDE`**

In `backend/app/db/nodes.py`, edit `_EXTRA_EXCLUDE`:

```python
_EXTRA_EXCLUDE: dict[type, set[str]] = {
    AgentFiringNode: {"created_at"},  # uses started_at/completed_at instead
}
```

- [ ] **Step 6: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: ALL PASS (38+1 = 39 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/kuzu_schema/001_nodes.cypher backend/app/db/schemas.py backend/app/db/nodes.py backend/tests/test_db/test_nodes.py
git commit -m "feat(spine): align AgentNode schema with Kuzu DDL (add created_at, enabled)"
```

---

## Task 2: agents.yaml config loader

**Files:**
- Create: `backend/agents.yaml.example`
- Create: `backend/app/agents/__init__.py` (empty)
- Create: `backend/app/agents/config.py`
- Create: `backend/tests/test_agents/__init__.py` (empty)
- Create: `backend/tests/test_agents/test_config.py`

- [ ] **Step 1: Write failing config test**

```python
# backend/tests/test_agents/test_config.py
from pathlib import Path

import pytest

from app.agents.config import AgentSpec, FleetConfig, load_fleet_config


def test_load_fleet_from_yaml(tmp_path: Path):
    cfg_file = tmp_path / "agents.yaml"
    cfg_file.write_text(
        """
agents:
  - id: cto-1
    role: cto
    persona: Senior CTO. Architecture decisions only.
    enabled: true
    tools:
      - vault_read
      - run_tests
    escalates_to: null

  - id: engineer-1
    role: engineer
    persona: Drafts code, runs tests, stages commits.
    enabled: true
    tools:
      - vault_read
      - vault_write
      - run_tests
      - stage_commits
    escalates_to: cto-1
        """
    )
    fleet = load_fleet_config(cfg_file)
    assert isinstance(fleet, FleetConfig)
    assert len(fleet.agents) == 2
    assert fleet.agents[0].id == "cto-1"
    assert "stage_commits" in fleet.agents[1].tools
    assert fleet.agents[1].escalates_to == "cto-1"


def test_load_fleet_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_fleet_config(tmp_path / "missing.yaml")


def test_agent_id_must_be_unique(tmp_path: Path):
    cfg_file = tmp_path / "agents.yaml"
    cfg_file.write_text(
        """
agents:
  - id: dup
    role: cto
    persona: a
    tools: []
  - id: dup
    role: engineer
    persona: b
    tools: []
        """
    )
    with pytest.raises(ValueError, match="duplicate agent id"):
        load_fleet_config(cfg_file)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_agents/test_config.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement config**

```python
# backend/app/agents/__init__.py
```
(empty)

```python
# backend/app/agents/config.py
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

ToolName = Literal[
    "vault_read", "vault_write", "run_tests", "stage_commits",
    "linear_read", "github_read",
]


class AgentSpec(BaseModel):
    id: str
    role: str
    persona: str
    enabled: bool = True
    tools: list[ToolName] = []
    escalates_to: str | None = None


class FleetConfig(BaseModel):
    agents: list[AgentSpec] = []

    @model_validator(mode="after")
    def _check_unique_ids(self):
        seen: set[str] = set()
        for a in self.agents:
            if a.id in seen:
                raise ValueError(f"duplicate agent id: {a.id}")
            seen.add(a.id)
        return self


def load_fleet_config(path: Path | str) -> FleetConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fleet config not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return FleetConfig.model_validate(data)
```

- [ ] **Step 4: Create example fleet**

```yaml
# backend/agents.yaml.example
# Default agent fleet for GigaBrain CNS v0.1.
# Each agent is a graph node with a queue. Agents fire on `fire.neuron` events
# whose `agent_role` matches.

agents:
  - id: cto-1
    role: cto
    persona: |
      Senior CTO. Owns architecture sparring and technical bet decisions.
      Escalates nothing — top of the technical chain.
    enabled: true
    tools:
      - vault_read
      - vault_write
    escalates_to: null

  - id: engineer-1
    role: engineer
    persona: |
      Senior backend engineer. Drafts code, runs tests, stages commits.
      Escalates to cto-1 for architecture decisions.
    enabled: true
    tools:
      - vault_read
      - vault_write
      - run_tests
      - stage_commits
    escalates_to: cto-1

  - id: pm-1
    role: pm
    persona: |
      Product manager. Curates Linear tickets, drafts sprint plans.
      Escalates to cto-1 for engineering tradeoffs.
    enabled: true
    tools:
      - vault_read
      - vault_write
      - linear_read
    escalates_to: cto-1

  - id: writer-1
    role: writer
    persona: |
      Drafts docs, blog posts, and PR descriptions in the Obsidian vault.
      Escalates nothing — outputs are always reviewed at the gate.
    enabled: true
    tools:
      - vault_read
      - vault_write
    escalates_to: null

  - id: inbox-1
    role: inbox
    persona: |
      Lightweight pre-spar / triage classifier. Cheap model, fast pass.
      Sees thoughts before they hit main sparring.
    enabled: true
    tools:
      - vault_read
    escalates_to: null
```

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/agents.yaml.example backend/app/agents/__init__.py backend/app/agents/config.py backend/tests/test_agents/__init__.py backend/tests/test_agents/test_config.py
git commit -m "feat(agents): yaml fleet config loader with unique-id validation"
```

---

## Task 3: Agent registry — sync yaml fleet → graph

**Files:**
- Create: `backend/app/agents/registry.py`
- Create: `backend/tests/test_agents/test_registry.py`

The registry has two responsibilities: (1) on startup, write each `AgentSpec` from the fleet config as an `AgentNode` in the graph (creating new ones, updating existing if config diverges); (2) provide query helpers (`list_agents`, `get_by_id`, `get_by_role`).

- [ ] **Step 1: Write failing registry test**

```python
# backend/tests/test_agents/test_registry.py
from pathlib import Path

import pytest

from app.agents.config import AgentSpec, FleetConfig
from app.agents.registry import AgentRegistry
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    yield {"conn": conn, "nodes": NodeRepository(conn)}
    conn.close()


def test_sync_creates_new_agents(stack):
    fleet = FleetConfig(agents=[
        AgentSpec(id="cto-1", role="cto", persona="..."),
        AgentSpec(id="engineer-1", role="engineer", persona="..."),
    ])
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(fleet)

    agents = reg.list_agents()
    ids = {a["id"] for a in agents}
    assert ids == {"cto-1", "engineer-1"}


def test_sync_updates_persona_for_existing_agent(stack):
    fleet1 = FleetConfig(agents=[AgentSpec(id="cto-1", role="cto", persona="v1")])
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(fleet1)

    fleet2 = FleetConfig(agents=[AgentSpec(id="cto-1", role="cto", persona="v2")])
    reg.sync(fleet2)

    fetched = reg.get_by_id("cto-1")
    assert fetched["persona"] == "v2"


def test_get_by_role_returns_all_matching(stack):
    fleet = FleetConfig(agents=[
        AgentSpec(id="eng-1", role="engineer", persona="a"),
        AgentSpec(id="eng-2", role="engineer", persona="b"),
        AgentSpec(id="cto-1", role="cto", persona="c"),
    ])
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(fleet)

    engineers = reg.get_by_role("engineer")
    assert len(engineers) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_agents/test_registry.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement registry**

```python
# backend/app/agents/registry.py
from app.agents.config import AgentSpec, FleetConfig
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import AgentNode


class AgentRegistry:
    def __init__(self, *, nodes: NodeRepository, conn: KuzuConnection):
        self.nodes = nodes
        self.conn = conn

    def sync(self, fleet: FleetConfig) -> None:
        """Idempotent: create-or-update each AgentSpec as an AgentNode."""
        for spec in fleet.agents:
            existing = self.nodes.get(spec.id, "Agent")
            if existing is None:
                self.nodes.create(AgentNode(
                    id=spec.id, role=spec.role, persona=spec.persona,
                    enabled=spec.enabled,
                ))
            else:
                # Update persona/role/enabled if changed
                self.conn.query(
                    "MATCH (a:Agent) WHERE a.id = $id "
                    "SET a.role = $role, a.persona = $persona, a.enabled = $enabled",
                    {"id": spec.id, "role": spec.role, "persona": spec.persona,
                     "enabled": spec.enabled},
                )

    def list_agents(self) -> list[dict]:
        return self.conn.query(
            "MATCH (a:Agent) RETURN a.id AS id, a.role AS role, "
            "a.persona AS persona, a.state AS state, a.enabled AS enabled, "
            "a.last_active AS last_active"
        )

    def get_by_id(self, agent_id: str) -> dict | None:
        return self.nodes.get(agent_id, "Agent")

    def get_by_role(self, role: str) -> list[dict]:
        return self.conn.query(
            "MATCH (a:Agent) WHERE a.role = $role RETURN a.id AS id, "
            "a.role AS role, a.persona AS persona, a.state AS state, "
            "a.enabled AS enabled",
            {"role": role},
        )
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_registry.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/registry.py backend/tests/test_agents/test_registry.py
git commit -m "feat(agents): registry syncs yaml fleet into graph (idempotent)"
```

---

## Task 4: Tool fence base interface

**Files:**
- Create: `backend/app/agents/tools/__init__.py` (empty)
- Create: `backend/app/agents/tools/base.py`
- Create: `backend/tests/test_agents/test_tools/__init__.py` (empty)
- Create: `backend/tests/test_agents/test_tools/test_base.py`

The tool fence has two layers: (1) per-agent declared tool list (from `agents.yaml`), and (2) global reversible-internal allowlist (hardcoded — anything outside this fence is denied at the tool layer). The base provides `Tool` ABC and a `FenceDeniedError` raised when an agent attempts a tool outside its allowlist OR outside the global fence.

- [ ] **Step 1: Write failing fence test**

```python
# backend/tests/test_agents/test_tools/test_base.py
import pytest

from app.agents.tools.base import (
    FenceDeniedError, GLOBAL_REVERSIBLE_INTERNAL, Tool, ToolContext,
    enforce_fence,
)


class _DummyTool(Tool):
    name = "dummy_safe"

    async def run(self, ctx: ToolContext, **kwargs) -> str:
        return "ok"


class _DummyExternal(Tool):
    name = "send_email"  # NOT in GLOBAL_REVERSIBLE_INTERNAL

    async def run(self, ctx: ToolContext, **kwargs) -> str:
        return "should not run"


def test_global_fence_lists_internal_tools_only():
    # All tools in the fence must be reversible-internal: vault writes, test runs,
    # local commits, reads. No external sends.
    assert "vault_read" in GLOBAL_REVERSIBLE_INTERNAL
    assert "vault_write" in GLOBAL_REVERSIBLE_INTERNAL
    assert "run_tests" in GLOBAL_REVERSIBLE_INTERNAL
    assert "stage_commits" in GLOBAL_REVERSIBLE_INTERNAL
    assert "send_email" not in GLOBAL_REVERSIBLE_INTERNAL


def test_enforce_fence_passes_when_in_global_and_in_agent_allowlist():
    # No exception raised
    enforce_fence(tool_name="vault_write", agent_allowlist=["vault_write", "run_tests"])


def test_enforce_fence_denies_outside_global():
    with pytest.raises(FenceDeniedError, match="not in global reversible-internal fence"):
        enforce_fence(tool_name="send_email", agent_allowlist=["send_email"])


def test_enforce_fence_denies_outside_agent_allowlist():
    with pytest.raises(FenceDeniedError, match="not in agent's allowlist"):
        enforce_fence(tool_name="run_tests", agent_allowlist=["vault_read"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_agents/test_tools/test_base.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement base**

```python
# backend/app/agents/tools/__init__.py
```
(empty)

```python
# backend/app/agents/tools/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass


# Hardcoded global fence: anything outside this set is denied regardless of
# what the agent's allowlist says. These are the only tools that v0.1 considers
# reversible-internal (no external side effects).
GLOBAL_REVERSIBLE_INTERNAL: frozenset[str] = frozenset({
    "vault_read",
    "vault_write",
    "run_tests",
    "stage_commits",
    "linear_read",
    "github_read",
})


class FenceDeniedError(RuntimeError):
    """Raised when a tool call is outside the fence (global or agent-level)."""


@dataclass
class ToolContext:
    """Per-call context passed into tools by the runtime."""
    agent_id: str
    firing_id: str
    vault_path: str         # absolute path to the user's vault
    repo_path: str | None = None  # absolute path to the active git repo (if any)


class Tool(ABC):
    """Base class for all agent tools."""
    name: str  # subclasses set this

    @abstractmethod
    async def run(self, ctx: ToolContext, **kwargs) -> str:
        ...


def enforce_fence(*, tool_name: str, agent_allowlist: Iterable[str]) -> None:
    """Raise FenceDeniedError if `tool_name` is denied at either fence layer."""
    if tool_name not in GLOBAL_REVERSIBLE_INTERNAL:
        raise FenceDeniedError(
            f"Tool {tool_name!r} not in global reversible-internal fence"
        )
    if tool_name not in agent_allowlist:
        raise FenceDeniedError(
            f"Tool {tool_name!r} not in agent's allowlist {list(agent_allowlist)!r}"
        )
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_tools/test_base.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/tools/ backend/tests/test_agents/test_tools/
git commit -m "feat(agents): tool fence base interface with global allowlist"
```

---

## Task 5: vault_read and vault_write tools

**Files:**
- Create: `backend/app/agents/tools/vault_read.py`
- Create: `backend/app/agents/tools/vault_write.py`
- Create: `backend/tests/test_agents/test_tools/test_vault_read.py`
- Create: `backend/tests/test_agents/test_tools/test_vault_write.py`

These are reversible-internal: reading any vault file, writing/appending to a vault file. v0.1 restriction: no path traversal outside the configured vault root.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_agents/test_tools/test_vault_read.py
from pathlib import Path

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.vault_read import VaultReadTool


@pytest.mark.asyncio
async def test_read_returns_file_contents(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("hello world")

    tool = VaultReadTool()
    ctx = ToolContext(agent_id="a", firing_id="f", vault_path=str(vault))
    out = await tool.run(ctx, path="note.md")
    assert out == "hello world"


@pytest.mark.asyncio
async def test_read_rejects_path_traversal(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "outside.md").write_text("secret")

    tool = VaultReadTool()
    ctx = ToolContext(agent_id="a", firing_id="f", vault_path=str(vault))
    with pytest.raises(ValueError, match="outside vault"):
        await tool.run(ctx, path="../outside.md")


@pytest.mark.asyncio
async def test_read_missing_file_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    tool = VaultReadTool()
    ctx = ToolContext(agent_id="a", firing_id="f", vault_path=str(vault))
    with pytest.raises(FileNotFoundError):
        await tool.run(ctx, path="missing.md")
```

```python
# backend/tests/test_agents/test_tools/test_vault_write.py
from pathlib import Path

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.vault_write import VaultWriteTool


@pytest.mark.asyncio
async def test_write_creates_file(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    tool = VaultWriteTool()
    ctx = ToolContext(agent_id="a", firing_id="f", vault_path=str(vault))
    await tool.run(ctx, path="drafts/note.md", content="hello")
    assert (vault / "drafts" / "note.md").read_text() == "hello"


@pytest.mark.asyncio
async def test_write_rejects_path_traversal(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    tool = VaultWriteTool()
    ctx = ToolContext(agent_id="a", firing_id="f", vault_path=str(vault))
    with pytest.raises(ValueError, match="outside vault"):
        await tool.run(ctx, path="../escape.md", content="x")


@pytest.mark.asyncio
async def test_write_overwrites_existing(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("v1")
    tool = VaultWriteTool()
    ctx = ToolContext(agent_id="a", firing_id="f", vault_path=str(vault))
    await tool.run(ctx, path="n.md", content="v2")
    assert (vault / "n.md").read_text() == "v2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_agents/test_tools/ -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement tools**

```python
# backend/app/agents/tools/vault_read.py
from pathlib import Path

from app.agents.tools.base import Tool, ToolContext


class VaultReadTool(Tool):
    name = "vault_read"

    async def run(self, ctx: ToolContext, *, path: str) -> str:
        vault = Path(ctx.vault_path).resolve()
        target = (vault / path).resolve()
        if not str(target).startswith(str(vault)):
            raise ValueError(f"Path {path!r} resolves outside vault")
        if not target.exists():
            raise FileNotFoundError(f"Vault file not found: {path}")
        return target.read_text()
```

```python
# backend/app/agents/tools/vault_write.py
from pathlib import Path

from app.agents.tools.base import Tool, ToolContext


class VaultWriteTool(Tool):
    name = "vault_write"

    async def run(self, ctx: ToolContext, *, path: str, content: str) -> str:
        vault = Path(ctx.vault_path).resolve()
        target = (vault / path).resolve()
        if not str(target).startswith(str(vault)):
            raise ValueError(f"Path {path!r} resolves outside vault")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"wrote {len(content)} bytes to {path}"
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_tools/test_vault_read.py tests/test_agents/test_tools/test_vault_write.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/tools/vault_read.py backend/app/agents/tools/vault_write.py backend/tests/test_agents/test_tools/test_vault_read.py backend/tests/test_agents/test_tools/test_vault_write.py
git commit -m "feat(agents): vault_read and vault_write tools with traversal guards"
```

---

## Task 6: run_tests and stage_commits tools

**Files:**
- Create: `backend/app/agents/tools/run_tests.py`
- Create: `backend/app/agents/tools/stage_commits.py`
- Create: `backend/tests/test_agents/test_tools/test_run_tests.py`
- Create: `backend/tests/test_agents/test_tools/test_stage_commits.py`

`run_tests` shells out to a configured test command in a configured repo. `stage_commits` does `git add <file>` + `git commit -m "<msg>"` in the repo — never pushes. Both bound to `ctx.repo_path`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_agents/test_tools/test_run_tests.py
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.run_tests import RunTestsTool


@pytest.mark.asyncio
async def test_run_tests_invokes_configured_command(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    tool = RunTestsTool(command="pytest -q")
    ctx = ToolContext(agent_id="a", firing_id="f",
                      vault_path=str(tmp_path / "v"), repo_path=str(repo))

    with patch("asyncio.create_subprocess_shell") as mock_proc:
        mock_proc.return_value.communicate = lambda: __aiter_dummy()
        # Provide a fake awaitable returning (b"out", b"")
        async def _fake_communicate():
            return (b"3 passed", b"")
        mock_proc.return_value.communicate = _fake_communicate
        mock_proc.return_value.returncode = 0
        out = await tool.run(ctx)
    assert "3 passed" in out


@pytest.mark.asyncio
async def test_run_tests_requires_repo_path(tmp_path: Path):
    tool = RunTestsTool(command="pytest")
    ctx = ToolContext(agent_id="a", firing_id="f",
                      vault_path=str(tmp_path), repo_path=None)
    with pytest.raises(ValueError, match="no repo_path"):
        await tool.run(ctx)


def __aiter_dummy():
    pass  # placeholder, never called
```

```python
# backend/tests/test_agents/test_tools/test_stage_commits.py
import subprocess
from pathlib import Path

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.stage_commits import StageCommitsTool


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)


@pytest.mark.asyncio
async def test_stage_and_commit_creates_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "f.py").write_text("x = 1\n")

    tool = StageCommitsTool()
    ctx = ToolContext(agent_id="a", firing_id="f",
                      vault_path=str(tmp_path / "v"), repo_path=str(repo))
    out = await tool.run(ctx, files=["f.py"], message="add f")
    assert "1 file changed" in out or "create mode" in out

    # Verify commit exists
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo,
                         capture_output=True, text=True)
    assert "add f" in log.stdout


@pytest.mark.asyncio
async def test_stage_commits_never_pushes(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "f.py").write_text("x = 1\n")

    push_called = []
    real_run = subprocess.run

    def _intercept(cmd, *args, **kwargs):
        if isinstance(cmd, list) and "push" in cmd:
            push_called.append(cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _intercept)

    tool = StageCommitsTool()
    ctx = ToolContext(agent_id="a", firing_id="f",
                      vault_path=str(tmp_path / "v"), repo_path=str(repo))
    await tool.run(ctx, files=["f.py"], message="add f")
    assert push_called == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_agents/test_tools/test_run_tests.py tests/test_agents/test_tools/test_stage_commits.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement run_tests**

```python
# backend/app/agents/tools/run_tests.py
import asyncio

from app.agents.tools.base import Tool, ToolContext


class RunTestsTool(Tool):
    name = "run_tests"

    def __init__(self, command: str = "pytest -q"):
        self.command = command

    async def run(self, ctx: ToolContext) -> str:
        if not ctx.repo_path:
            raise ValueError("run_tests requires ToolContext.repo_path; got None")
        proc = await asyncio.create_subprocess_shell(
            self.command,
            cwd=ctx.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        body = (stdout or b"").decode() + (stderr or b"").decode()
        suffix = "" if proc.returncode == 0 else f"\n[exit code {proc.returncode}]"
        return body + suffix
```

- [ ] **Step 4: Implement stage_commits**

```python
# backend/app/agents/tools/stage_commits.py
import subprocess

from app.agents.tools.base import Tool, ToolContext


class StageCommitsTool(Tool):
    name = "stage_commits"

    async def run(self, ctx: ToolContext, *, files: list[str], message: str) -> str:
        if not ctx.repo_path:
            raise ValueError("stage_commits requires ToolContext.repo_path; got None")
        if not files:
            raise ValueError("stage_commits requires at least one file")
        # Stage
        subprocess.run(["git", "add", *files], cwd=ctx.repo_path, check=True)
        # Commit (no push, ever)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=ctx.repo_path, capture_output=True, text=True, check=False,
        )
        return result.stdout + result.stderr
```

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_tools/ -v`
Expected: PASS (all tool tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/tools/run_tests.py backend/app/agents/tools/stage_commits.py backend/tests/test_agents/test_tools/test_run_tests.py backend/tests/test_agents/test_tools/test_stage_commits.py
git commit -m "feat(agents): run_tests and stage_commits tools (no push)"
```

---

## Task 7: AgentRuntime (pydantic-ai Agent + tool fence)

**Files:**
- Create: `backend/app/agents/prompts.py`
- Create: `backend/app/agents/runtime.py`
- Create: `backend/tests/test_agents/test_runtime.py`

`AgentRuntime` wraps `pydantic_ai.Agent` with: (a) the role's system prompt, (b) the agent's declared tools wrapped in fence enforcement, (c) Anthropic backend per `LLMConfig`. Uses pydantic-ai 1.x API: `output_type=`, `result.output`, `AnthropicProvider`.

- [ ] **Step 1: Write failing runtime test (mocked)**

```python
# backend/tests/test_agents/test_runtime.py
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.config import AgentSpec
from app.agents.runtime import AgentRuntime, AgentRunResult
from app.config import LLMConfig


@pytest.mark.asyncio
async def test_runtime_runs_agent_and_returns_output():
    spec = AgentSpec(id="eng-1", role="engineer", persona="drafts code",
                     tools=["vault_read"])
    cfg = LLMConfig(provider="anthropic", model="claude-sonnet-4-6",
                    api_key_env="ANTHROPIC_API_KEY")

    mock_output = AgentRunResult(summary="drafted thing", actions_taken=[])
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
        with patch("app.agents.runtime.Agent") as MockAgent:  # noqa: N806
            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=type("R", (), {"output": mock_output})())
            runtime = AgentRuntime(
                spec=spec, llm_cfg=cfg,
                vault_path="/tmp/vault", repo_path=None,
            )
            out = await runtime.run(firing_id="f_1", task_summary="add /capture")

    assert out.summary == "drafted thing"


@pytest.mark.asyncio
async def test_runtime_rejects_tool_outside_global_fence():
    spec = AgentSpec(id="eng-1", role="engineer", persona="drafts code",
                     tools=["send_email"])  # not in global fence
    cfg = LLMConfig(provider="anthropic", model="x", api_key_env="X")
    with pytest.raises(ValueError, match="not in global reversible-internal fence"):
        AgentRuntime(
            spec=spec, llm_cfg=cfg,
            vault_path="/tmp/vault", repo_path=None,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_agents/test_runtime.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement prompts and runtime**

```python
# backend/app/agents/prompts.py
ROLE_PROMPT_TEMPLATES: dict[str, str] = {
    "engineer": """You are a senior backend engineer agent in GigaBrain.
You draft code, run tests, and stage commits — but you NEVER push or merge.
Every external action requires the leader's approval through the consciousness gate.
{persona}

When you receive a task:
1. Read relevant context from the vault and the current task summary.
2. Draft the work.
3. Run tests if applicable.
4. Stage commits if the work is code.
5. Return a structured result with what you did.
""",
    "writer": """You are a writing agent in GigaBrain. You draft docs, blog posts,
and PR descriptions in the vault. You never publish or send anything externally.
{persona}
""",
    "pm": """You are a PM agent in GigaBrain. You curate Linear tickets and draft
sprint plans in the vault. You never close, archive, or assign tickets externally.
{persona}
""",
    "cto": """You are the CTO agent in GigaBrain. You spar architecture decisions
and write decision records in the vault. You make no external technical commitments.
{persona}
""",
    "inbox": """You are the inbox triage agent. You produce a single-sentence
classification of incoming thoughts. Cheap and fast.
{persona}
""",
}


def build_system_prompt(role: str, persona: str) -> str:
    template = ROLE_PROMPT_TEMPLATES.get(role)
    if template is None:
        return persona
    return template.format(persona=persona)
```

```python
# backend/app/agents/runtime.py
import os

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from app.agents.config import AgentSpec
from app.agents.prompts import build_system_prompt
from app.agents.tools.base import GLOBAL_REVERSIBLE_INTERNAL
from app.config import LLMConfig


class AgentAction(BaseModel):
    """One concrete action the agent took during a run."""
    tool: str
    summary: str


class AgentRunResult(BaseModel):
    """Structured output from an agent run."""
    summary: str
    actions_taken: list[AgentAction] = []


class AgentRuntime:
    def __init__(
        self,
        *,
        spec: AgentSpec,
        llm_cfg: LLMConfig,
        vault_path: str,
        repo_path: str | None,
    ):
        # Pre-flight: every tool the agent declares must be in the global fence
        for tool_name in spec.tools:
            if tool_name not in GLOBAL_REVERSIBLE_INTERNAL:
                raise ValueError(
                    f"Tool {tool_name!r} declared by agent {spec.id!r} "
                    f"is not in global reversible-internal fence"
                )
        self.spec = spec
        self.vault_path = vault_path
        self.repo_path = repo_path

        api_key = os.environ.get(llm_cfg.api_key_env, "") or None
        if llm_cfg.provider != "anthropic":
            raise ValueError(f"Unsupported LLM provider for agents: {llm_cfg.provider}")
        model = AnthropicModel(
            llm_cfg.model,
            provider=AnthropicProvider(api_key=api_key),
        )
        system_prompt = build_system_prompt(spec.role, spec.persona)
        self._agent: Agent[None, AgentRunResult] = Agent(
            model=model,
            system_prompt=system_prompt,
            output_type=AgentRunResult,
        )
        # Tool registration is deferred to v0.2 — pydantic-ai's tool API differs
        # across 1.x minors. v0.1 ships agents that draft + summarise without
        # invoking real tools (see Plan 2 follow-up).

    async def run(self, *, firing_id: str, task_summary: str) -> AgentRunResult:
        user_msg = f"Task (firing_id={firing_id}):\n{task_summary}"
        result = await self._agent.run(user_msg)
        return result.output
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_runtime.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/prompts.py backend/app/agents/runtime.py backend/tests/test_agents/test_runtime.py
git commit -m "feat(agents): AgentRuntime wraps pydantic-ai with role prompts and fence preflight"
```

---

## Task 8: Agent worker — subscribe to fire.neuron and process queue

**Files:**
- Create: `backend/app/agents/worker.py`
- Create: `backend/tests/test_agents/test_worker.py`

The worker subscribes to `fire.neuron` events. For each event, it: (1) finds an enabled agent with the matching role, (2) creates an `AgentFiring` node, (3) updates the agent state to `working`, (4) runs `AgentRuntime`, (5) writes outputs back as graph edges (`Agent -[produced]-> AgentFiring -[fired-from]-> Thought`), (6) marks the firing complete and the agent idle, (7) publishes a `firing.complete` event.

- [ ] **Step 1: Write failing worker test**

```python
# backend/tests/test_agents/test_worker.py
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.agents.config import AgentSpec, FleetConfig
from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRunResult
from app.agents.worker import AgentWorker
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.events.bus import EventBus
from app.events.schemas import FireNeuron


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bus = EventBus()
    yield {"conn": conn, "nodes": nodes, "edges": edges, "bus": bus,
           "vault": str(tmp_path / "vault"), "repo": None}
    conn.close()


@pytest.mark.asyncio
async def test_worker_processes_fire_neuron_for_matching_role(stack, monkeypatch):
    # Seed the fleet
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(FleetConfig(agents=[
        AgentSpec(id="eng-1", role="engineer", persona="x"),
    ]))

    # Stub AgentRuntime.run via monkeypatch on the class
    fake_result = AgentRunResult(summary="drafted /capture endpoint")
    async def fake_run(self, *, firing_id, task_summary):
        return fake_result
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", fake_run)
    # Also stub the constructor to skip real LLM init
    def fake_init(self, *, spec, llm_cfg, vault_path, repo_path):
        self.spec = spec
        self.vault_path = vault_path
        self.repo_path = repo_path
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.__init__", fake_init)

    worker = AgentWorker(
        registry=reg,
        nodes=stack["nodes"], edges=stack["edges"], bus=stack["bus"],
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=FleetConfig(agents=[AgentSpec(id="eng-1", role="engineer", persona="x")]),
        vault_path=stack["vault"], repo_path=stack["repo"],
    )
    worker.attach()

    await stack["bus"].publish(FireNeuron(
        thought_id="t_1", agent_role="engineer", task_summary="add /capture",
    ))
    await asyncio.sleep(0.2)

    firings = stack["conn"].query("MATCH (f:AgentFiring) RETURN f.id AS id, "
                                  "f.outcome AS outcome, f.agent_id AS agent_id")
    assert len(firings) == 1
    assert firings[0]["agent_id"] == "eng-1"
    assert firings[0]["outcome"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_agents/test_worker.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement worker**

```python
# backend/app/agents/worker.py
import logging
from datetime import datetime, timezone

from app.agents.config import FleetConfig
from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRuntime
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.nodes import NodeRepository
from app.db.schemas import AgentFiringNode, EdgeRecord, NodeType
from app.events.bus import EventBus
from app.events.schemas import FireNeuron

log = logging.getLogger(__name__)


class AgentWorker:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        nodes: NodeRepository,
        edges: EdgeRepository,
        bus: EventBus,
        llm_cfg: LLMConfig,
        fleet: FleetConfig,
        vault_path: str,
        repo_path: str | None,
    ):
        self.registry = registry
        self.nodes = nodes
        self.edges = edges
        self.bus = bus
        self.llm_cfg = llm_cfg
        self.fleet = fleet
        self.vault_path = vault_path
        self.repo_path = repo_path

    def attach(self) -> None:
        self.bus.subscribe("fire.neuron", self._handle_fire_neuron)

    async def _handle_fire_neuron(self, event: FireNeuron) -> None:
        try:
            agents = self.registry.get_by_role(event.agent_role)
            enabled = [a for a in agents if a.get("enabled")]
            if not enabled:
                log.warning("No enabled agents for role %s; dropping firing for thought %s",
                            event.agent_role, event.thought_id)
                return
            agent_row = enabled[0]  # v0.1: pick first; v0.2 = round-robin
            agent_id = agent_row["id"]

            spec = next((s for s in self.fleet.agents if s.id == agent_id), None)
            if spec is None:
                log.warning("Agent %s in graph but not in fleet config; dropping", agent_id)
                return

            firing = AgentFiringNode(
                agent_id=agent_id, trace_id=f"trace_{event.thought_id}",
            )
            self.nodes.create(firing)
            # Edges: Agent -[produced]-> AgentFiring; AgentFiring -[fired-from]-> Thought
            self.edges.create(EdgeRecord(
                from_id=agent_id, from_type=NodeType.AGENT,
                to_id=firing.id, to_type=NodeType.AGENT_FIRING,
                edge_type="produced", confidence=1.0,
            ))
            self.edges.create(EdgeRecord(
                from_id=firing.id, from_type=NodeType.AGENT_FIRING,
                to_id=event.thought_id, to_type=NodeType.THOUGHT,
                edge_type="fired-from", confidence=1.0,
            ))

            runtime = AgentRuntime(
                spec=spec, llm_cfg=self.llm_cfg,
                vault_path=self.vault_path, repo_path=self.repo_path,
            )
            try:
                result = await runtime.run(
                    firing_id=firing.id, task_summary=event.task_summary,
                )
                outcome = "success"
                summary = result.summary
            except Exception:
                log.exception("Agent run failed for firing %s", firing.id)
                outcome = "failed"
                summary = "agent run raised; see logs"

            self.nodes.conn.query(
                "MATCH (f:AgentFiring) WHERE f.id = $id "
                "SET f.outcome = $outcome, f.completed_at = $completed_at",
                {"id": firing.id, "outcome": outcome,
                 "completed_at": datetime.now(timezone.utc)},
            )
        except Exception:
            log.exception("Worker failed processing fire.neuron for thought %s",
                          event.thought_id)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_worker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/worker.py backend/tests/test_agents/test_worker.py
git commit -m "feat(agents): worker subscribes to fire.neuron, runs agent, records firing"
```

---

## Task 9: Wire agent fleet + worker into main.py lifespan

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py` (add `agents_yaml_path` and `vault_path`/`repo_path`)
- Create: `backend/tests/test_agents/test_e2e_fire_neuron.py`

The lifespan in main.py loads the fleet config, syncs it via `AgentRegistry`, and attaches `AgentWorker` to the bus alongside the existing `SparringEngine`. End-to-end test: a fire.neuron event leads to an AgentFiring being recorded.

- [ ] **Step 1: Add fleet/vault/repo paths to config**

Edit `backend/app/config.py`. Add a section:

```python
class AgentsConfig(BaseModel):
    yaml_path: str = "./agents.yaml"
    vault_path: str = "./vault"
    repo_path: str | None = None


class GigaBrainConfig(BaseModel):
    db: DBConfig = DBConfig()
    embeddings: EmbeddingsConfig = EmbeddingsConfig()
    llm: LLMConfig = LLMConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    gigaflow: GigaFlowConfig = GigaFlowConfig()
    agents: AgentsConfig = AgentsConfig()
```

Update `backend/gigabrain.yaml.example` to add the `agents:` section with these defaults.

- [ ] **Step 2: Wire worker in lifespan**

In `backend/app/main.py`, after the SparringEngine block, add:

```python
from app.agents.config import load_fleet_config, FleetConfig
from app.agents.registry import AgentRegistry
from app.agents.worker import AgentWorker

# Load fleet — fall back to empty if file missing (no agents will fire)
fleet_path = Path(cfg.agents.yaml_path)
fleet = load_fleet_config(fleet_path) if fleet_path.exists() else FleetConfig()
registry = AgentRegistry(nodes=nodes, conn=conn)
registry.sync(fleet)
worker = AgentWorker(
    registry=registry, nodes=nodes, edges=edges, bus=bus,
    llm_cfg=cfg.llm, fleet=fleet,
    vault_path=cfg.agents.vault_path, repo_path=cfg.agents.repo_path,
)
worker.attach()
app.state.registry = registry
app.state.worker = worker
app.state.fleet = fleet
```

- [ ] **Step 3: E2E test**

```python
# backend/tests/test_agents/test_e2e_fire_neuron.py
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.config import AgentSpec, FleetConfig
from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRunResult
from app.agents.worker import AgentWorker
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.events.bus import EventBus
from app.events.schemas import FireNeuron


@pytest.mark.asyncio
async def test_fire_neuron_creates_firing_and_edges(tmp_path: Path, monkeypatch):
    conn = KuzuConnection(str(tmp_path / "e2e.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bus = EventBus()

    # Pre-existing thought
    thought = ThoughtNode(content="add /capture endpoint", source="cli")
    nodes.create(thought)

    # Fleet
    spec = AgentSpec(id="eng-1", role="engineer", persona="x")
    fleet = FleetConfig(agents=[spec])
    AgentRegistry(nodes=nodes, conn=conn).sync(fleet)

    # Stub the runtime
    fake_result = AgentRunResult(summary="drafted endpoint")
    async def fake_run(self, *, firing_id, task_summary):
        return fake_result
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", fake_run)
    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.__init__",
        lambda self, *, spec, llm_cfg, vault_path, repo_path: setattr(self, "spec", spec),
    )

    worker = AgentWorker(
        registry=AgentRegistry(nodes=nodes, conn=conn),
        nodes=nodes, edges=edges, bus=bus,
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=fleet, vault_path=str(tmp_path / "vault"), repo_path=None,
    )
    worker.attach()

    await bus.publish(FireNeuron(thought_id=thought.id, agent_role="engineer",
                                 task_summary="add /capture"))
    await asyncio.sleep(0.2)

    # Firing exists
    firings = conn.query("MATCH (f:AgentFiring) RETURN f.id AS id, "
                         "f.outcome AS outcome, f.agent_id AS agent_id")
    assert len(firings) == 1
    assert firings[0]["outcome"] == "success"

    # Both edges exist
    firing_id = firings[0]["id"]
    produced = conn.query(
        "MATCH (a:Agent)-[r:REL]->(f:AgentFiring) "
        "WHERE r.edge_type = 'produced' AND f.id = $fid RETURN a.id AS a",
        {"fid": firing_id},
    )
    assert len(produced) == 1
    assert produced[0]["a"] == "eng-1"

    fired_from = conn.query(
        "MATCH (f:AgentFiring)-[r:REL]->(t:Thought) "
        "WHERE r.edge_type = 'fired-from' AND f.id = $fid RETURN t.id AS t",
        {"fid": firing_id},
    )
    assert len(fired_from) == 1
    assert fired_from[0]["t"] == thought.id

    conn.close()
```

- [ ] **Step 4: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/config.py backend/gigabrain.yaml.example backend/tests/test_agents/test_e2e_fire_neuron.py
git commit -m "feat(agents): wire fleet sync + worker into main.py lifespan"
```

---

## Task 10: `/agents` HTTP endpoints

**Files:**
- Create: `backend/app/agents/api.py`
- Create: `backend/tests/test_agents/test_api.py`

Endpoints:
- `GET /agents` — list all agents with state, queue depth, last_active
- `POST /agents/{id}/pause` — set state to `paused` (worker filters paused agents)
- `POST /agents/{id}/resume` — set state to `idle`

Swap-into-seat (claim/handback) is more involved — defer to v0.2.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_agents/test_api.py
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.api import build_agents_router
from app.agents.config import AgentSpec, FleetConfig
from app.agents.registry import AgentRegistry
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    reg = AgentRegistry(nodes=nodes, conn=conn)
    reg.sync(FleetConfig(agents=[
        AgentSpec(id="eng-1", role="engineer", persona="x"),
    ]))
    app = FastAPI()
    app.include_router(build_agents_router(registry=reg, conn=conn))
    yield app
    conn.close()


def test_list_agents(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == "eng-1"


def test_pause_and_resume(configured_app):
    client = TestClient(configured_app)
    r1 = client.post("/agents/eng-1/pause")
    assert r1.status_code == 200

    body = client.get("/agents").json()
    assert body[0]["state"] == "paused"

    client.post("/agents/eng-1/resume")
    body = client.get("/agents").json()
    assert body[0]["state"] == "idle"


def test_pause_unknown_agent_returns_404(configured_app):
    client = TestClient(configured_app)
    resp = client.post("/agents/missing/pause")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test (fails)**

Run: `cd backend && uv run pytest tests/test_agents/test_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement endpoints**

```python
# backend/app/agents/api.py
from fastapi import APIRouter, HTTPException

from app.agents.registry import AgentRegistry
from app.db.kuzu import KuzuConnection


def build_agents_router(*, registry: AgentRegistry, conn: KuzuConnection) -> APIRouter:
    router = APIRouter()

    @router.get("/agents")
    def list_agents() -> list[dict]:
        return registry.list_agents()

    @router.post("/agents/{agent_id}/pause")
    def pause(agent_id: str) -> dict:
        if registry.get_by_id(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"agent {agent_id} not found")
        conn.query(
            "MATCH (a:Agent) WHERE a.id = $id SET a.state = 'paused'",
            {"id": agent_id},
        )
        return {"id": agent_id, "state": "paused"}

    @router.post("/agents/{agent_id}/resume")
    def resume(agent_id: str) -> dict:
        if registry.get_by_id(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"agent {agent_id} not found")
        conn.query(
            "MATCH (a:Agent) WHERE a.id = $id SET a.state = 'idle'",
            {"id": agent_id},
        )
        return {"id": agent_id, "state": "idle"}

    return router
```

- [ ] **Step 4: Mount in main.py lifespan**

In `backend/app/main.py`, alongside the other `app.include_router(...)` calls inside `lifespan`:

```python
from app.agents.api import build_agents_router
app.include_router(build_agents_router(registry=registry, conn=conn))
```

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/test_agents/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Update worker to skip paused agents**

In `backend/app/agents/worker.py`, change the agent selection:

```python
enabled = [a for a in agents if a.get("enabled") and a.get("state") != "paused"]
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/api.py backend/app/agents/worker.py backend/app/main.py backend/tests/test_agents/test_api.py
git commit -m "feat(agents): /agents HTTP endpoints (list, pause, resume)"
```

---

## Task 11: `gigabrain agents` CLI

**Files:**
- Create: `backend/app/cli/__init__.py` (empty)
- Create: `backend/app/cli/agents.py`
- Create: `backend/tests/test_cli/__init__.py` (empty)
- Create: `backend/tests/test_cli/test_agents.py`
- Modify: `backend/pyproject.toml` (register CLI entry)

Pretty-prints the fleet at a glance:

```
$ gigabrain agents
cto-1     cto       idle    enabled  -
eng-1     engineer  idle    enabled  pm-1: cto-1
pm-1      pm        idle    enabled  cto-1
writer-1  writer    idle    enabled  -
inbox-1   inbox     idle    enabled  -
```

- [ ] **Step 1: Failing CLI test**

```python
# backend/tests/test_cli/test_agents.py
from pathlib import Path

from click.testing import CliRunner

from app.cli.agents import cli


def test_list_agents_command(tmp_path: Path):
    cfg = tmp_path / "gigabrain.yaml"
    cfg.write_text(f"""
db:
  kuzu_path: {tmp_path}/test.kuzu
  vector_path: {tmp_path}/test-vec.sqlite
agents:
  yaml_path: {tmp_path}/agents.yaml
  vault_path: {tmp_path}/vault
""")
    (tmp_path / "agents.yaml").write_text("""
agents:
  - id: eng-1
    role: engineer
    persona: x
""")
    runner = CliRunner()
    result = runner.invoke(cli, ["agents"], env={"GIGABRAIN_CONFIG": str(cfg)})
    assert result.exit_code == 0
    assert "eng-1" in result.output
    assert "engineer" in result.output
```

- [ ] **Step 2: Run test (fails)**

Run: `cd backend && uv run pytest tests/test_cli/test_agents.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement CLI**

```python
# backend/app/cli/__init__.py
```
(empty)

```python
# backend/app/cli/agents.py
from pathlib import Path

import click

from app.agents.registry import AgentRegistry
from app.config import load_config
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository


@click.group()
def cli():
    """GigaBrain CLI."""


@cli.command("agents")
@click.option("--config", envvar="GIGABRAIN_CONFIG", default="gigabrain.yaml")
def list_agents(config: str):
    """List the configured agent fleet and their current state."""
    cfg = load_config(Path(config))
    conn = KuzuConnection(cfg.db.kuzu_path)
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    reg = AgentRegistry(nodes=nodes, conn=conn)
    rows = reg.list_agents()
    if not rows:
        click.echo("(no agents — check agents.yaml at " + cfg.agents.yaml_path + ")")
        return
    for row in rows:
        click.echo(
            f"{row['id']:<10} {row['role']:<10} {row.get('state','idle'):<8} "
            f"{'enabled' if row.get('enabled', True) else 'disabled'}"
        )
    conn.close()


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Register CLI entry in pyproject.toml**

Add to `backend/pyproject.toml` under `[project]`:

```toml
[project.scripts]
gigabrain = "app.cli.agents:cli"
```

Add `click>=8.1` to dependencies.

- [ ] **Step 5: Run test**

Run: `cd backend && uv run pytest tests/test_cli/test_agents.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/cli/ backend/tests/test_cli/ backend/pyproject.toml
git commit -m "feat(agents): gigabrain agents CLI for fleet inspection"
```

---

## Task 12: OTel attribute injection on agent firings + clean up unused deps

**Files:**
- Modify: `backend/app/agents/worker.py` (inject `gigabrain.firing_id`, `gigabrain.agent_id`, `gigabrain.agent_role`)
- Modify: `backend/pyproject.toml` (drop unused `pydantic-settings`)

This addresses two follow-ups from Plan 1's final review:
1. The custom OTel attribute injection that the spec called for
2. Removing the `pydantic-settings` dep that was added but never used

- [ ] **Step 1: Inject attributes in the worker**

In `backend/app/agents/worker.py`, wrap the runtime call in an OTel span and inject the attributes:

```python
from opentelemetry import trace
from app.telemetry.otel import inject_gigabrain_attrs

# ...
async def _handle_fire_neuron(self, event: FireNeuron) -> None:
    tracer = trace.get_tracer("gigabrain.agents.worker")
    with tracer.start_as_current_span("agent.run") as span:
        inject_gigabrain_attrs(
            span,
            firing_id=None,  # set after AgentFiring is created
            agent_id=None,   # set after spec is resolved
            agent_role=event.agent_role,
            outcome=None,    # set after run completes
        )
        # ... existing logic, with inject_gigabrain_attrs called again after firing.id is known ...
```

(Read the existing worker code and integrate carefully — you'll likely want to set the attributes on the same span at multiple points as info becomes available.)

- [ ] **Step 2: Drop pydantic-settings**

In `backend/pyproject.toml`, remove `pydantic-settings>=2.2` from `dependencies`. Run `cd backend && uv lock` to update the lockfile.

- [ ] **Step 3: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/agents/worker.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(agents): OTel gigabrain.* attrs on agent runs; drop unused pydantic-settings"
```

---

## Done — Plan 2 deliverables

After this plan:

- Agents are first-class graph nodes loaded from `agents.yaml` at startup
- `AgentWorker` subscribes to `fire.neuron` events and runs the matching agent through `AgentRuntime` (pydantic-ai)
- Tool fence enforced at two layers (declared allowlist + global reversible-internal set), with 4 tools: `vault_read`, `vault_write`, `run_tests`, `stage_commits`
- Each agent run records an `AgentFiring` node with `produced` (Agent→AgentFiring) and `fired-from` (AgentFiring→Thought) edges
- `/agents`, `/agents/{id}/pause`, `/agents/{id}/resume` HTTP endpoints
- `gigabrain agents` CLI for fleet inspection
- OTel `gigabrain.*` attributes attached to every agent run for GigaFlow consumption
- ~20 new tests (config, registry, runtime, worker, tools, API, CLI, e2e)

**Estimated build:** 1.5-2 weeks for v0.1.

**Deferred to v0.2 (not in this plan):**

- Tool registration with pydantic-ai (current AgentRuntime.run passes a string but doesn't actually wire tools to the LLM — the agent will produce structured summaries but won't invoke real tools yet). v0.2 wires tools via pydantic-ai's `Agent.tool` decorator after the API stabilizes.
- "Swap into agent's seat" — claim a task from agent's queue, do it yourself, hand back. Requires more state on AgentFiring (assigned_to_user flag, etc.) — defer.
- Round-robin or load-balanced agent selection when multiple agents share a role.
- Linear/GitHub read tools (depend on Plan 5 adapters).
- Agent escalation chain (escalates_to is captured in config but not used at runtime).
