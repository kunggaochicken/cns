# GigaBrain CNS v2 — Design Spec

**Date:** 2026-05-06
**Status:** Draft for review
**Supersedes:** GigaBrain Obsidian plugin v1 (shipped 2026-04-30)

---

## Vision

GigaBrain is a **central nervous system for an agentic team**. It is open source, self-hostable, and designed to be paired with [GigaFlow](https://github.com/GigaFlow-AI/gigaflow) (separate repo) to create a self-improving feedback loop.

The shift from v1: v1 framed GigaBrain as a "delegation console" that replaced the terminal. Dogfooding revealed that the right unification is different — **Claude Code is the right surface for giving direction; GigaBrain should be the surface for finding where to direct attention** and the substrate for the brain that holds it all together.

This spec defines v2 as a clean reframe with the CNS metaphor taken literally.

## Core metaphor (literal, not decorative)

- **Synapse** — every thought enters the brain instantly, regardless of source surface
- **Activation** — the brain retrieves relevant memories on every thought (past bets, decisions, code, conflicts, conversations)
- **Sparring circuit** — every thought is automatically sparred against history and classified: *clear*, *conflicting*, or *novel*
- **Neuron firing** — clear thoughts trigger reactive agents that do real (reversible-internal) work
- **Consciousness gate** — only ambiguous decisions reach the user; everything else fires below awareness
- **Plasticity** — the graph densifies with traceable causation; agents tune over time via GigaFlow training signals

## Vision in one diagram

```
[any surface] → POST /capture
                      │
                      ▼
                ┌──────────┐
                │  thought │ (graph node, embedded)
                └────┬─────┘
                     │
              sparring engine
              (Claude + retrieval)
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
     CLEAR       CONFLICT      NOVEL
        │            │            │
        ▼            ▼            ▼
   fire neuron   gate item   encode/index
   (agent does   (you decide  (new bet
    real work)    in brain)    candidate)

  All actions emit OpenTelemetry GenAI spans →
  GigaFlow ingests → reward signals → optimizations flow back
```

---

## Section 1 — Substrate & data model

The graph database is the source of truth for **structure** (nodes, edges, provenance, agent state, gate items). Content lives in three places, with the graph holding metadata + pointers.

### Stack

- **Graph DB:** [KuzuDB](https://kuzudb.com/) — embedded, single-file, Cypher-like query language, scales to billions of edges. Open source, no daemon.
- **Vector index:** [sqlite-vec](https://github.com/asg017/sqlite-vec) (or [LanceDB](https://lancedb.github.io/lancedb/) if performance demands it) — embedded, OSS
- **Embeddings:** pluggable. Default: local `nomic-embed-text` via Ollama. Configurable to OpenAI / Voyage / etc.

### Node types

All node types are flat in v0.1; categorical refactor is deferred to v0.2 once usage patterns emerge.

| Type | Where content lives | Notes |
|---|---|---|
| `thought` | Graph (inline) | Raw user input, pre-spar |
| `bet` | Obsidian vault | Long-form strategic decisions (markdown) |
| `task` | Linear | Bite-size tickets |
| `decision` | Graph (inline) | Resolved gate items |
| `conflict` | Graph (inline) | Sparring output identifying contradictions |
| `outcome` | Graph (inline) | Result of an agent firing or decision |
| `agent_firing` | Graph (inline) | One neuron event w/ OTel trace ID |
| `code_change` | GitHub commit/PR (pointer) | Pointer + summary |
| `conversation` | Graph or vault | Captured back-and-forth |
| `doc` | Obsidian vault | Free-form long-form |
| `gate_item` | Graph (inline) | Pending decisions surfaced to the user |
| `agent` | Graph | Agent identity + queue + role + state |

### Edge types

Typed, directional, with provenance fields (`created_at`, `created_by`, `confidence`).

- `caused-by` / `led-to` — causation
- `sparred-against` — which prior nodes a sparring run pulled
- `fired-from` — a thought → an agent_firing
- `resolved-by` — a gate_item → a decision
- `supersedes` / `contradicts` / `aligns-with` — relational
- `referenced-by` — citation, not causation
- `produced` — an agent_firing → a code_change / outcome / doc / decision

### Embedding strategy

Every text-bearing node gets embedded on creation. Sparring queries pull top-K (default 12) semantically similar nodes plus their immediate graph neighborhood (depth 2), then sends the bundle to an LLM for the actual spar.

### Why graph DB rather than file-only

A pure markdown-vault approach (v1's substrate) cannot sustain:
- Millions of provenance edges
- Real graph queries ("show me all gate items linked to bets owned by CTO that conflict with bets created in the last 30 days") at sub-second latency
- Native attribution joins for GigaFlow integration

Kuzu makes these millisecond-scale and gives the brain-view UI native Cypher to query.

---

## Section 2 — Capture & sparring engine

### Capture pipeline (hot path, < 100ms)

```
[any surface] → POST /capture { content, source, metadata }
              → create `thought` node + embed
              → emit `thought.created` event
              → return { node_id, status: "sparring" }
```

**Source adapters** (pluggable):
- `pwa` — mobile/desktop web app
- `voice` — STT layer (defer to v0.2 — Whisper local or OpenAI API)
- `web` — desktop web capture
- `cli` — `gigabrain capture "..."`
- `obsidian` — file-watcher on the vault
- `linear` — webhook on ticket create
- `github` — webhook on commit/PR

All funnel into the same `/capture` endpoint with a `source` field.

### Sparring engine (warm path, 1-5s, async)

```python
on thought.created:
    1. similarity_search(thought.embedding, top_k=12)
    2. expand_neighborhood(matches, depth=2)
    3. spar_result = llm_spar(thought, context_bundle)
       # Returns:
       # {
       #   classification: "clear" | "conflict" | "novel",
       #   reasoning: "free text",
       #   edges_to_record: [{type, target_id, confidence}, ...],
       #   suggested_action: { agent_role, task_summary } | None
       # }
    4. write edges (always at minimum: `sparred-against` to retrieved nodes)
    5. route based on classification (see below)
```

The sparring LLM is implemented via [pydantic-ai](https://ai.pydantic.dev/) (which natively emits OpenTelemetry GenAI spans, the input shape GigaFlow consumes). v0.1 model: Claude Sonnet 4.6. v0.2+: fine-tuned models from GigaFlow.

### Implicit vs explicit sparring

Both modes use the same engine; only the trigger differs:

- **Implicit** — every captured thought is auto-sparred (default behavior)
- **Explicit** — user picks an existing node and triggers a re-spar (button in brain view, or `gigabrain spar <node-id>` CLI)

### Routing

| Classification | Action |
|---|---|
| `clear` + actionable | Emit `fire-neuron` event → matching agent picks up, drafts work, creates `agent_firing` node |
| `clear` + not actionable | Stays indexed in the graph, already linked to relevant context |
| `conflict` | Create `gate_item` node, link to conflicting bet/decision, raise priority, notifier may push |
| `novel` | Stays indexed; optional gate item if it looks like a new bet candidate |

### Latency tiers

- **Hot:** capture (< 100ms — write thought + queue event)
- **Warm:** sparring (1-5s — async, result lands in brain)
- **Cold:** hot spot scan, periodic re-sparring of stale thoughts (every N minutes)

### Real-time brain updates

The brain view subscribes via SSE/websocket to graph events. New nodes/edges appear live. This makes "I see neurons firing" visceral.

### Sparring quality

Sparring quality is the limiting factor on the entire system's usefulness. v0.1 mitigations:
- The LLM never deletes — every spar action is reversible by re-sparring or by the user in the brain view
- Every spar emits OTel spans (GigaFlow can score them later)
- Gate decisions feed back as RLHF labels for v0.2+ fine-tuning

---

## Section 3 — Agents & autonomy

### Agent identity model

Each agent is a graph node with:

```yaml
id: engineer-1
role: engineer
persona: |
  Senior backend engineer. Drafts code, runs tests, prepares commits.
  Escalates anything that requires architecture decisions.
tool_capabilities:
  - read_files
  - write_to_vault
  - run_tests
  - stage_commits
  - read_linear
  - read_github
escalates_to: cto
queue: []           # edge type `queued-on`
state: idle         # idle | working | paused | escalated
current_firing: null
```

Configured via `.gigabrain/agents.yaml`. The format is self-documenting; each entry includes `description`, `responsibilities`, and inline comments. CLI:

```
$ gigabrain agents
cto         engineering decisions, architecture        idle    queue: 0
engineer    drafts code, runs tests, stages commits   working queue: 3 → cur: bet_auth_pivot
pm          Linear curation, sprint prep               paused  queue: 12
writer      drafts docs/PRs/blog                       idle    queue: 0
inbox       lightweight pre-spar / triage              idle    queue: 0
```

### Default agent fleet (v0.1)

- `cto` — engineering decisions, architecture sparring, technical bet sparring
- `engineer` — drafts code changes, runs tests, prepares commits
- `pm` — Linear ticket curation, sprint planning prep
- `writer` — drafts docs, blog posts, PR descriptions
- `inbox` — lightweight pre-spar / triage classifier (cheap model, fast pass)

User adds/removes/customizes via `agents.yaml`.

### Agent runtime

```
agent-worker process:
  on fire-neuron event:
    1. dequeue task from agent's queue
    2. update agent.state = working, write agent_firing node
    3. invoke pydantic-ai agent w/ tools (Claude API or configured LLM)
       ↑ emits OTel GenAI spans automatically
    4. record outputs as graph nodes (code_change, doc, decision-draft)
    5. update agent_firing.outcome, emit firing.complete event
```

v0.1 deployment: a single `agent-worker` process polls all agent queues and routes events to the right agent based on `agent_role`. Splitting into per-agent processes is a v0.2 scaling concern, not a v0.1 requirement. LLM provider: Claude API by default (BYO `ANTHROPIC_API_KEY`), pluggable via pydantic-ai to OpenAI / Ollama / etc.

### Reversible-internal fence

Enforced at the tool layer (not the prompt). Agents declare what tools they want; the runtime denies anything outside their allowlist + the global fence.

| Tool | Allowed reflexively | Requires gate |
|---|---|---|
| Read files / Linear / Obsidian | ✓ | — |
| Write to vault (drafts, notes) | ✓ | — |
| Run tests / lint / typecheck | ✓ | — |
| Stage commits (no push) | ✓ | — |
| Push to remote / open PR | — | ✓ |
| Send email / Slack / external | — | ✓ |
| Modify Linear ticket status | ✓ within own queue | ✓ for marking shipped |
| Spend money / call paid APIs | — | ✓ |
| Filesystem outside vault | — | ✓ |

Anything denied auto-creates a gate item with the proposed action, so the user can approve/veto/resteer.

### "Swap into agent's seat"

Click an agent in the brain view → agent panel (queue + current firing + recent history). Actions:

- `pause` — agent stops auto-firing
- `claim task` — move firing from agent.queue to user.queue (you do it)
- `spar with agent` — side chat where you can question/redirect
- `hand back` — resume agent on the task you were doing

Implementation: graph mutations + event emission, no special infrastructure beyond what's already there.

### OpenTelemetry GenAI instrumentation

Every LLM call emits a span via pydantic-ai's built-in instrumentation. Spans tagged with:

- `gigabrain.thought_id`
- `gigabrain.firing_id`
- `gigabrain.gate_item_id` (when relevant)
- `gigabrain.agent_id`
- `gigabrain.agent_role`
- `gigabrain.outcome` (populated on completion)
- `gigabrain.classification` (from sparring)

OTLP endpoint configurable: defaults to local file (works without GigaFlow), overridable to GigaFlow's OTLP receiver.

---

## Section 4 — Brain view UI

The brain view is the primary surface. Same graph state, two renderings: **desktop graph view** for deep crawl, **mobile inbox view** for triage.

### Desktop graph view (primary)

- Force-directed graph canvas filling most of the viewport
- Nodes color-coded by type:
  - 🟣 bet · 🟡 gate item (lit) · 🔴 conflict · 🟢 thought · 🟪 agent firing · 🔵 code change · 🟦 doc
- Hot spots shown as radial glow + pulse animation around clusters of high activity
- Gate items glow yellow with urgency-scaled intensity
- Top bar: live counts (`⚡ 3 gate items` · `🔥 2 hot spots`)
- Right panel (slide-in on node select): full node detail + edges + zoom-in actions
- Bottom: capture bar (always-reachable text input + voice button + spar button)

### Mobile inbox view (responsive web v0.1, native PWA v0.2)

- Top tabs: Gate (default) · Hot · Recent
- Gate items as cards with inline actions: `approve`, `veto`, `resteer`, `zoom`
- Each card: urgency tier, age, owning agent, summary, drafted output (if any)
- Bottom nav: Gate · Brain (graph view, gesture-zoomable) · **+** (large, central — capture button) · Agents
- Capture button supports text + voice (v0.2) + paste

### Zoom-in affordances

Click a node in the graph view → opens the right surface:

| Node type | Zoom destination |
|---|---|
| `bet` | Obsidian — opens the bet's markdown file |
| `task` | Linear — opens the ticket |
| `agent_firing` | Agent panel — see the trace, swap into seat |
| `code_change` | GitHub — opens commit/PR |
| `gate_item` | In-place resolve panel (right sidebar) |
| `conflict` | In-place resolve panel + linked nodes highlighted |
| `thought` / `decision` / `outcome` | In-place expanded view |

### Real-time updates

UI subscribes to graph events via SSE. New nodes/edges animate in as they're created.

---

## Section 5 — GigaFlow integration

GigaBrain works fully without GigaFlow. Connecting GigaFlow turns observed trajectories into trained-better agents.

### OTel GenAI span attributes

GigaBrain agents use pydantic-ai, which emits the full standard `gen_ai.*` OTel GenAI namespace (model, prompt, completion, token counts, latency) automatically. GigaBrain adds its own custom attributes alongside, prefixed `gigabrain.*`:

```
gigabrain.thought_id
gigabrain.firing_id
gigabrain.gate_item_id
gigabrain.agent_id
gigabrain.agent_role
gigabrain.outcome           # success | partial | failed
gigabrain.classification    # clear | conflict | novel
```

These let GigaFlow join trajectories to the brain's graph state.

### Gate decisions as RLHF labels

Emitted as a separate event class so GigaFlow can pair them to trajectories:

```json
{
  "event": "gigabrain.gate.resolved",
  "gate_item_id": "g_8af",
  "decision": "approved",
  "reasoning": "free text — what tipped the call",
  "alternative": null,
  "resolved_at": "2026-05-06T...",
  "resolved_by": "user",
  "trajectory_span_ids": ["span_1", "span_2"]
}
```

GigaFlow's `aif_rewards` package consumes these directly to compute composite rewards.

### Optimization signal injection

For v0.1, simple. GigaFlow writes an *optimization manifest* (JSON file or HTTP endpoint):

```json
{
  "agent_role": "engineer",
  "recommended_model": "claude-sonnet-4-6-finetuned-2026-05-01",
  "recommended_prompt_patch": "...",
  "based_on_trajectories": 412,
  "expected_lift": 0.18
}
```

GigaBrain reads this on startup + periodically. v0.1: recommendation surfaces as a gate item ("apply this optimization?"). v0.2+: auto-apply with rollback.

### Connection config

`gigabrain.yaml`:

```yaml
telemetry:
  otlp_endpoint: file:///var/log/gigabrain/traces  # default — works without GigaFlow
  # otlp_endpoint: http://localhost:4318           # uncomment to export to GigaFlow

gigaflow:
  enabled: false                                   # opt-in
  manifest_url: http://gigaflow.local:8000/optimizations/gigabrain
  poll_interval_minutes: 60
```

---

## Section 6 — MVP scope (v0.1)

### Ships in v0.1

- Single-user, single-leader (recursive org tree is v0.2+)
- Capture from: web app (desktop responsive), CLI, file-watcher (Obsidian vault), Linear webhook, GitHub webhook
- Mobile = responsive web (works but not PWA-optimized)
- Graph DB substrate (KuzuDB), vector index (sqlite-vec), embeddings via Ollama or OpenAI
- Sparring engine (Claude Sonnet via pydantic-ai), implicit + explicit modes
- Default agent fleet (cto, engineer, pm, writer, inbox), reversible-internal fence
- Brain view (desktop graph + responsive mobile inbox), zoom-in to Obsidian / Linear / agent seat
- OTel GenAI emission (works locally; GigaFlow opt-in)
- Gate decisions emit RLHF-shaped labels
- `docker-compose up` self-hosting

### Defers to v0.2+

- GigaFlow auto-applied optimizations (v0.1 surfaces as gate item)
- Native PWA (installable, offline-capable)
- Voice STT
- Recursive org tree (CTOs spawning VPs spawning engineers)
- Multi-user / team mode
- Categorical refactor of node types
- Auto-promotion of "novel" thoughts to bets without user confirmation

### Explicit non-goals for v0.1

- Fine-tuned models (we collect labels; GigaFlow does the training, separate timeline)
- Replacing Obsidian or Linear (we integrate, we don't replicate)
- Cross-org collaboration / sharing

### Estimated build

6-10 weeks for v0.1.

- **Critical path:** spine (graph DB schema + capture API + sparring service) — 3-4 weeks
- **Parallelizable after spine:** brain view UI, agent runtime, GigaFlow integration, Obsidian/Linear/GitHub adapters
- **Dogfood-readiness:** end of week 4 (spine + minimal UI + 2 agents)

---

## Open questions

These are deliberately deferred — the design is buildable as specified, but these are worth deciding before or during implementation:

1. **Hot spot scoring formula** — what weighted combination of (open conflicts + agent activity rate + gate queue depth + code churn + node novelty) marks something as "hot"? Probably hand-tuned in v0.1, learned via GigaFlow in v0.2.

2. **Embedding model default** — Ollama+nomic gives self-hosters zero-dependency, but quality lags OpenAI/Voyage. Should v0.1 ship with a quality-vs-OSS-purity tradeoff toggle?

3. **Conflict resolution UX details** — when you `resteer` a gate item, does that create a new bet, modify an existing bet's frontmatter, or just record a decision node with the override?

4. **Backup / export** — single-file Kuzu DB makes backup trivial (copy the file), but a `gigabrain export --format json` for portability is worth specifying.

5. **Multi-tenant / team mode v0.2 shape** — does the recursive org tree share one Kuzu DB or have per-leader DBs that sync?

---

## What this replaces

- **GigaBrain Obsidian plugin v1** — the plugin still works for read-only browsing of an existing vault, but v0.2 of the plugin will become a thin Obsidian view on top of the v2 graph DB. The action bars (Dispatch / Spar / Walk) are vestigial in the v2 model — gate items handle all of those flows.
- **`cns` CLI commands** (`bet`, `execute`, `spar`, `reviews accept`) — replaced by `gigabrain` CLI subcommands that talk to the same backend the web app uses.

Existing user-facing concepts (bets, briefs, conflicts, sparring) carry over identically — the rename is `cns` → `gigabrain` and the implementation moves to the graph DB.
