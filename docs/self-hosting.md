# Self-hosting GigaBrain

GigaBrain ships as a single docker-compose stack. The whole brain runs on
one machine — your laptop, a home server, or a small VPS.

## Prerequisites

- Docker Engine ≥ 24, with the `compose` plugin
- ~4 GB RAM (Ollama's `nomic-embed-text` is small but Kuzu likes headroom)
- An Anthropic API key

## First-time install

```bash
git clone https://github.com/kunggaochicken/GigaBrain.git
cd GigaBrain
cp .env.example .env
# Edit .env to set ANTHROPIC_API_KEY=sk-ant-...

docker compose up -d
docker compose logs -f gigabrain
```

First boot takes 2–5 minutes (Ollama pulls the embed model). Once
`gigabrain-app` says it's listening on `0.0.0.0:8000` (the container's
internal port), point a browser at `http://localhost:8001` for the brain
view — the host-side port is `8001` (the container's `8000` is mapped to
the host's `8001` to avoid colliding with other services).

## First capture

```bash
curl -X POST http://localhost:8001/capture \
  -H 'content-type: application/json' \
  -d '{"content": "hello brain", "source": "manual"}'
```

You should see the thought appear in the brain view within a second.

## Pointing it at an Obsidian vault

1. Mount your vault into the container by editing `docker-compose.yml`:

   ```yaml
   gigabrain:
     volumes:
       - gigabrain-data:/data
       - /path/to/your/Obsidian:/data/vault  # add this line
   ```

2. Flip `watchers.obsidian.enabled: true` in `backend/gigabrain.docker.yaml`
   (or override at runtime by mounting your own config and pointing
   `GIGABRAIN_CONFIG` at it).

3. `docker compose restart gigabrain`. Edits to `.md` files in the vault
   now fire as thoughts.

## Webhooks

Set `LINEAR_WEBHOOK_SECRET` and/or `GITHUB_WEBHOOK_SECRET` in `.env`, then
restart the stack. Point Linear at `https://<your-host>/webhooks/linear`
and GitHub at `https://<your-host>/webhooks/github`. Both require an HTTPS
reverse proxy in front of the bare 8001 port — use Caddy or Nginx; that's
out of scope for v0.1.

## CLI capture from another machine

The `gigabrain` CLI inside the container is reachable via `docker compose
exec`, but in practice you'll want the CLI on your laptop pointed at the
hosted backend. Install the Python package locally and set
`capture.backend_url` in your local `gigabrain.yaml`:

```yaml
capture:
  backend_url: https://gigabrain.yourdomain.com
```

Then `gigabrain capture "first thought"` posts to your hosted brain.

## Resetting

```bash
docker compose down -v   # wipes gigabrain-data AND ollama-models volumes
```

## Where data lives

| Path inside container          | Volume           | Contents                    |
|--------------------------------|------------------|-----------------------------|
| `/data/gigabrain.kuzu`         | `gigabrain-data` | Graph DB                    |
| `/data/gigabrain-vec.sqlite`   | `gigabrain-data` | Vector index                |
| `/data/traces/`                | `gigabrain-data` | OTel trace files            |
| `/data/vault/`                 | `gigabrain-data` | Optional Obsidian mount     |
| `/root/.ollama/`               | `ollama-models`  | Embedding model weights     |

To back up just the brain (skip the Ollama model — it's recoverable on
boot):

```bash
docker run --rm \
  -v gigabrain-data:/d \
  -v $(pwd):/host \
  alpine tar czf /host/gigabrain-backup.tgz /d
```

## Parallel agent dispatch

By default, the v2 agent worker runs one agent at a time. To process multiple
`fire.neuron` events concurrently, set a `dispatch:` block in your `agents.yaml`:

```yaml
dispatch:
  max_parallel: 3        # up to 3 agent runs at once across the whole fleet
  per_role:
    cto: 1               # never run two CTO agents concurrently
    engineer: 2          # up to 2 engineer agents concurrently
```

Semantics:

- **Per-role behavior:** by default, firings for the same role are serialized
  (never overlap, even when the global cap would allow it) — this avoids two
  agents in the same role racing on a shared workspace. Use `per_role` to
  permit limited concurrency within a role (`per_role: {engineer: 2}` allows
  two engineer agents at once) or to tighten the cap further than the global
  default would.
- **Failure isolation:** an agent run raising an exception marks that firing as
  `outcome=failed` in the graph and does not abort sibling runs.
- **Progress events:** every run emits `agent.run.started` and
  `agent.run.completed` events over the SSE `/stream` channel, tagged with
  `firing_id` so the brain view can correlate.
- **Live state:** `GET /agents/inflight` returns the dispatcher's current
  snapshot: `[{firing_id, role, started_at}]`.

## Troubleshooting

- **`gigabrain-app` exits with `ANTHROPIC_API_KEY is required`** — `.env`
  is missing or the key isn't set. Compose refuses to bring up the
  service to fail loud and early.
- **`ollama-init` hangs** — `ollama pull` is a large download on first
  run. Watch its logs; allow up to ~5 minutes on a slow link.
- **Frontend 404s on `/`** — make sure the frontend stage built clean.
  `docker compose build gigabrain --no-cache` and watch for npm errors.
