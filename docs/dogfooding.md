# Dogfooding GigaBrain v2

You're running the v2 docker stack against a real vault for the first time and want
to know what to do once it's up. For first-time install (Docker, `.env`, vault
mount, parallel-dispatch config), see [self-hosting.md](self-hosting.md). This
doc picks up after `docker compose up -d` is healthy and `http://localhost:8001`
shows an empty brain view.

This is a **living document during the v0.2 dogfood phase**. Once a workflow
stabilizes here, it migrates into [README.md](../README.md) as canonical user
guidance.

## The dogfood loop

A typical dogfood session has four moves:

### 1. Capture a thought

Any of:
- The CLI: `gigabrain capture "thought here"` (the host-side CLI, defaults to
  `http://localhost:8001`)
- The brain view's capture bar at the top of `http://localhost:8001`
- A vault edit, if the Obsidian watcher is enabled
- A webhook (Linear / GitHub — needs an HTTPS reverse proxy, see
  [self-hosting.md §Webhooks](self-hosting.md#webhooks))

Within ~1 s the thought should appear as a `ThoughtNode` in the brain view.

### 2. Watch it route

The sparring engine decides whether a thought should fire an agent and which
role. Stream the event bus to watch it happen:

```bash
curl -N http://localhost:8001/stream
```

You'll see `thought.created`, `gate.created`, `fire.neuron`, and (if an agent
runs) `agent.run.started` / `agent.run.completed` events fly by.

### 3. Inspect agent runs

Currently-running firings:

```bash
curl http://localhost:8001/agents/inflight
# → [{"firing_id": "f_abc", "role": "cto", "started_at": 1715634567.12}]
```

The configured fleet:

```bash
curl http://localhost:8001/agents
```

### 4. Resolve gate items

When the engine asks for a human decision (a "gate item"), it appears in the
brain view as a pulsing node. Use the gate-resolve panel to approve / veto /
resteer.

## Test plan for v0.2 features

Exercises worth running specifically to validate Plans 01–07:

### Parallel agent dispatch (Plan 07)

Make sure your config has `dispatch.max_parallel >= 2` (see
[self-hosting.md §Parallel agent dispatch](self-hosting.md#parallel-agent-dispatch)),
then fire three captures targeting different roles in rapid succession:

```bash
for role in cto engineer pm; do
  curl -X POST http://localhost:8001/capture \
    -H 'content-type: application/json' \
    -d "{\"content\": \"test $role thought\", \"source\": \"manual\"}" &
done
wait

# In another shell, immediately:
curl http://localhost:8001/agents/inflight
```

Expect up to 3 concurrent firings (one per role). Two captures to the same
role should serialize — `max_seen` per role stays at 1 unless you've set a
`per_role` override above 1.

### Obsidian vault watcher (Plan 05)

With the watcher enabled, edit any `.md` file in your vault. Within
`debounce_seconds` (default 2.0), a new `ThoughtNode` appears with
`source=obsidian` and `metadata.vault_path` set.

### Source webhooks (Plan 04)

If you've set up Linear / GitHub webhooks: create a Linear ticket or open a
GitHub PR. A `ThoughtNode` with the matching `source` tag should land in the
brain view.

## Known gaps — watch for these

Documented architectural limitations you'll bump into. Each is a candidate
input for a v0.2 plan.

### BetNode is wired but unfed

The brain view has a `BetNode` type, but the watcher ingests bet markdown as
generic `ThoughtNode`s. **Your v1 bets won't appear as bets in the v2 brain
view.** Closing this gap is the leading Plan 08 candidate.

**Notice it as:** you edit `Brain/Bets/bet_X.md` and see a generic thought
node, not a typed bet.

### Queued firings invisible to `/agents/inflight`

The endpoint only shows firings that have acquired the dispatcher's role
gate. Firings queued behind a saturated `max_parallel` are invisible
(their `AgentFiringNode` rows exist in the graph, but the endpoint omits
them). Flagged in Plan 07's final review.

**Notice it as:** POST 5 captures with `max_parallel=2`, `/agents/inflight`
shows 2.

### Vault watcher false-fires

The watcher excludes `.git/`, `.obsidian/`, and `*.gigabrain*` by default.
Other auto-generated files (`.DS_Store`, `~$foo.docx` Office lockfiles,
editor swap files) may sneak through and create useless thought nodes.

**Notice it as:** `ThoughtNode`s with content you didn't author.

### Embedding cost on big vaults

Ollama is local (free, no API cost) but a vault with thousands of notes is
slow to backfill. The watcher only embeds on edit, so steady-state load is
light — but a fresh deploy against a large vault will peg Ollama for
minutes.

**Notice it as:** Ollama container at high CPU after `docker compose down -v`
and a re-mount of a large vault.

### `agent.run` OTel span includes gate wait

The span opens before `dispatcher.dispatch()` is awaited, so its duration
includes time waiting for the role gate (not just actual agent execution).
If you use span duration as a latency metric, it over-reports under
contention.

**Notice it as:** a sequential pair of CTO firings shows the second span at
~2× the agent's actual wall time.

## The friction log

Keep a markdown file (in your vault or elsewhere) called `friction.md`.
Every time you think:

- "Huh, that's weird"
- "I expected X but got Y"
- "I wish this did Z"
- "Why is this slow?"
- "I don't trust this output"

…write it down. The format that's worked in this codebase:

```markdown
## 2026-05-13

**What I did:** edited `bet_neurips_sprint.md` to flip `status` from active
to deferred.
**What happened:** new generic `ThoughtNode` created.
**What I expected:** the corresponding `BetNode` would update.
**Want:** v2 should re-parse frontmatter on `.md` edits and reconcile.
```

After ~1 week, group entries by theme. Themes that recur 3+ times across
days are strong Plan 08 candidates. One-offs are usually polish — batch them
into a single polish PR rather than planning each.

## When dogfooding suggests a new plan

Call a new plan when you have:

- A recurring friction (3+ entries on the same theme)
- A hard blocker (you wanted to do X and couldn't)
- A surprise that contradicts the architecture (the BetNode gap is one such
  — flagged in audit, confirmed by usage)

Don't write a plan for one-off polish; batch those.

## Reset / rinse / repeat

Start fresh (preserves your `.env` and any local config overrides):

```bash
docker compose down -v   # -v wipes named volumes — graph + vector store gone
docker compose up -d
```

The Ollama embed model is cached in the `ollama-models` volume, so a
re-pull is only needed if you wipe that volume separately.

To wipe everything including model cache:

```bash
docker compose down -v
docker volume rm gigabrain_ollama-models  # check actual name with `docker volume ls`
docker compose up -d
```

## Promotion path to README

When a section here stops changing — i.e., the workflow is stable, the
gotchas no longer surprise anyone, and the friction log isn't generating
new entries for that area — promote it:

1. Copy the stabilized section into `README.md` (likely under a new
   "Using GigaBrain" section, replacing the current 8-line quickstart).
2. Trim or delete the section from this file with a note linking to the
   README.
3. The remaining content in this doc stays as "dogfood-phase guidance"
   — known gaps, friction-log practice, when-to-plan — which is meta and
   not user-facing.

Eventually this file shrinks to a meta doc about how to dogfood future
versions; the user-facing "how to use GigaBrain" lives in the README.
