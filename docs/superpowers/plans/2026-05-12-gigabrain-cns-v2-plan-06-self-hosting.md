# GigaBrain CNS v2 — Plan 6: Self-Hosting (docker-compose)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docker-compose up` the one-command install for the GigaBrain v0.1 CNS. After this plan ships, a new user clones the repo, copies `.env.example` to `.env`, sets `ANTHROPIC_API_KEY`, runs `docker-compose up`, and has the brain view at `http://localhost:8000` with Ollama on the side for local embeddings.

**Architecture:** Two services:

- **`gigabrain`** — multi-stage Dockerfile that builds the React frontend in a `node:20` stage and copies the built static assets into a `python:3.12-slim` runtime stage. The runtime stage installs the backend with `uv sync --frozen --no-dev`, mounts a host volume at `/data` for the Kuzu DB + sqlite-vec + OTel traces, and runs `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **`ollama`** — official `ollama/ollama:latest` image. On first start, an init job pulls the `nomic-embed-text` model. Persistent named volume for `~/.ollama` so the model survives container rebuilds.

The backend reaches Ollama on the docker-compose internal network at `http://ollama:11434`, configured via env var that overrides `embeddings.base_url` (or a docker-specific config file).

Single port exposed to the host: `8000` (the FastAPI app, which also serves the frontend SPA via `mount_frontend`). No reverse proxy in v0.1 — users add their own Caddy/Nginx if they want TLS.

**Tech Stack:** Docker + docker-compose v2. Python 3.12-slim base. node:20-alpine for the frontend build stage. Ollama official image. No new application dependencies — this is pure infra.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-gigabrain-cns-v2-design.md`](../specs/2026-05-06-gigabrain-cns-v2-design.md) §6 (MVP scope: `docker-compose up` self-hosting).

**Lessons from Plan 1–5 baked in:**
- The frontend is served from the backend via `mount_frontend(app)` — no separate frontend container needed in v0.1.
- Frontend build emits to `frontend/dist/` — copy that into the Python image at the path `mount_frontend` looks for (verify the actual path before writing the Dockerfile).
- Default config paths must be writable by the container's runtime user. The compose volume must mount over `./data` and the Dockerfile must create that directory with permissive ownership.
- Pre-commit hooks reformat. Run `uv run python -m pytest tests/` once before opening the PR.
- The `gigabrain.yaml` shipped in the docker image needs to point Ollama at `http://ollama:11434`, not `http://localhost:11434`. Use an env var override or a docker-specific config file (the latter is cleaner — see Task 4).

---

## Scope: 1 PR, ~8 tasks

This is mostly file-creation infrastructure, not TDD application code. Tests here are integration smokes — "does it build?", "does the container respond on /health?". CI runs them with `docker-compose --profile ci`.

---

## File structure

```
.
├── Dockerfile                           # Multi-stage: node build + python runtime
├── docker-compose.yml                   # gigabrain + ollama + optional init job
├── .env.example                         # Template for ANTHROPIC_API_KEY, etc.
├── .dockerignore
├── backend/
│   └── gigabrain.docker.yaml            # Docker-mode config: ollama at ollama:11434, data under /data
└── docs/
    └── self-hosting.md                  # How to install + first capture + reset
```

---

## Task 1: Author the backend `Dockerfile`

**Files:**
- Create: `Dockerfile` (repo root)
- Create: `.dockerignore` (repo root)

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.6

# ---- Stage 1: build the React frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim AS runtime

# uv is the dependency manager
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

# System deps Kuzu and sqlite-vec need
RUN apt-get update && apt-get install -y --no-install-recommends \
        libstdc++6 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (cached layer)
COPY backend/pyproject.toml backend/uv.lock ./backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev

# Copy backend source
COPY backend/ /app/backend/

# Copy built frontend assets to where mount_frontend looks for them.
# VERIFY: backend/app/api/frontend.py reads from a specific path — match it here.
COPY --from=frontend-build /src/dist /app/backend/static/frontend

# Data dir (mounted as a volume in docker-compose)
RUN mkdir -p /data && chown -R 1000:1000 /data
ENV GIGABRAIN_CONFIG=/app/backend/gigabrain.docker.yaml
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Run as a non-root user
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> **VERIFICATION required during execution:** check `backend/app/api/frontend.py` for the static-assets path it serves (e.g. `Path(__file__).parents[2] / "static" / "frontend"`). If it's different, update both the `COPY --from=frontend-build` target AND the `mount_frontend` path resolution. Do NOT skip this check.

- [ ] **Step 2: Write `.dockerignore`**

```
**/node_modules
**/.venv
**/__pycache__
**/.pytest_cache
**/.git
**/.claude
**/dist
docs/superpowers/plans
*.log
```

- [ ] **Step 3: Smoke-build the image locally**

```bash
docker build -t gigabrain:test .
```

Expected: builds without error in 2–5 minutes (mostly download time for npm + uv deps).

- [ ] **Step 4: Smoke-run the container**

```bash
docker run --rm -p 8000:8000 -v $(pwd)/.docker-data:/data gigabrain:test
```

In another terminal:

```bash
curl http://localhost:8000/health
# expected: {"status": "ok"} or whatever /health returns today
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat(docker): multi-stage Dockerfile (node frontend build + python runtime)

Verified locally: builds clean, /health responds on 8000. mount_frontend serves
the built React SPA from /app/backend/static/frontend."
```

---

## Task 2: Author the `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml` (repo root)

- [ ] **Step 1: Write the compose file**

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: gigabrain-ollama
    restart: unless-stopped
    volumes:
      - ollama-models:/root/.ollama
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 5s
      timeout: 2s
      retries: 12

  ollama-init:
    image: ollama/ollama:latest
    container_name: gigabrain-ollama-init
    depends_on:
      ollama:
        condition: service_healthy
    entrypoint: ["/bin/sh", "-c", "OLLAMA_HOST=ollama:11434 ollama pull nomic-embed-text"]
    restart: "no"

  gigabrain:
    build: .
    image: gigabrain:local
    container_name: gigabrain-app
    restart: unless-stopped
    depends_on:
      ollama-init:
        condition: service_completed_successfully
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY is required — see .env.example}
      - LINEAR_WEBHOOK_SECRET=${LINEAR_WEBHOOK_SECRET:-}
      - GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET:-}
    volumes:
      - gigabrain-data:/data
    ports:
      - "8000:8000"

volumes:
  ollama-models:
  gigabrain-data:
```

- [ ] **Step 2: Smoke-bring-up**

```bash
cp .env.example .env  # Then edit .env to set ANTHROPIC_API_KEY
docker-compose up -d
docker-compose logs -f gigabrain
```

Expected: `ollama-init` exits 0 after pulling the embed model; `gigabrain-app` starts and serves on `localhost:8000`.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(docker): docker-compose.yml — gigabrain + ollama + init"
```

---

## Task 3: Author `.env.example`

**Files:**
- Create: `.env.example` (repo root)

- [ ] **Step 1: Write the file**

```bash
# GigaBrain CNS — environment template
# Copy to .env and fill in. .env is gitignored.

# REQUIRED: Anthropic API key for the sparring engine + agents.
ANTHROPIC_API_KEY=

# OPTIONAL: HMAC secrets for inbound webhooks. Leave blank to disable
# the corresponding /webhooks/* endpoint (it will reject all requests).
LINEAR_WEBHOOK_SECRET=
GITHUB_WEBHOOK_SECRET=
```

- [ ] **Step 2: Update `.gitignore`** (if `.env` is not already ignored)

Confirm with:

```bash
grep -n "^\.env\b\|^\.env$" .gitignore
```

If not present, append:

```
.env
.docker-data/
```

- [ ] **Step 3: Commit**

```bash
git add .env.example .gitignore
git commit -m "feat(docker): .env.example template + gitignore .env + .docker-data"
```

---

## Task 4: Author `backend/gigabrain.docker.yaml`

**Files:**
- Create: `backend/gigabrain.docker.yaml`

This is the config the docker image uses (selected by `GIGABRAIN_CONFIG=/app/backend/gigabrain.docker.yaml` in the Dockerfile). It differs from `gigabrain.yaml.example` only in the paths and ollama URL.

- [ ] **Step 1: Write the file**

```yaml
db:
  kuzu_path: /data/gigabrain.kuzu
  vector_path: /data/gigabrain-vec.sqlite

embeddings:
  provider: ollama
  model: nomic-embed-text
  base_url: http://ollama:11434

llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY

telemetry:
  otlp_endpoint: file:///data/traces

gigaflow:
  enabled: false

agents:
  yaml_path: /app/backend/agents.yaml.example  # User can override via volume mount
  vault_path: /data/vault                       # User mounts their own vault here
  repo_path: null

capture:
  backend_url: http://localhost:8000
  timeout_seconds: 5.0

webhooks:
  linear_secret_env: LINEAR_WEBHOOK_SECRET
  github_secret_env: GITHUB_WEBHOOK_SECRET

watchers:
  obsidian:
    enabled: false
    debounce_seconds: 2.0
    ignore_patterns:
      - .git/*
      - .obsidian/*
      - "*.gigabrain*"
```

- [ ] **Step 2: Verify the container picks it up**

Rebuild and re-up:

```bash
docker-compose down
docker-compose up --build -d
docker exec gigabrain-app cat /app/backend/gigabrain.docker.yaml | head -5
docker exec gigabrain-app ls /data
```

Expected: the config is in place; `/data` is writable and contains the kuzu DB after the first capture.

- [ ] **Step 3: Commit**

```bash
git add backend/gigabrain.docker.yaml
git commit -m "feat(docker): backend/gigabrain.docker.yaml — docker-mode config

Same shape as gigabrain.yaml.example but with /data paths and ollama hostname
that match the docker-compose network."
```

---

## Task 5: Author `docs/self-hosting.md`

**Files:**
- Create: `docs/self-hosting.md`

- [ ] **Step 1: Write the doc**

```markdown
# Self-hosting GigaBrain

GigaBrain ships as a single docker-compose stack. The whole brain runs on one
machine — your laptop, a home server, or a small VPS.

## Prerequisites

- Docker Engine ≥ 24, with the `compose` plugin
- ~4 GB RAM (Ollama's `nomic-embed-text` is small but Kuzu likes headroom)
- An Anthropic API key (free tier is enough to dogfood)

## First-time install

```bash
git clone https://github.com/kunggaochicken/GigaBrain.git
cd GigaBrain
cp .env.example .env
# Edit .env to set ANTHROPIC_API_KEY=sk-ant-...

docker-compose up -d
docker-compose logs -f gigabrain
```

First boot takes 2–5 minutes (Ollama pulls the embed model). Once
`gigabrain-app` says it's listening on `0.0.0.0:8000`, point a browser at
`http://localhost:8000` for the brain view.

## First capture

```bash
curl -X POST http://localhost:8000/capture \
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
   (or override at runtime by mounting your own config and setting
   `GIGABRAIN_CONFIG=/data/my-config.yaml`).

3. `docker-compose restart gigabrain`. Edits to `.md` files in the vault
   now fire as thoughts.

## Webhooks

Set `LINEAR_WEBHOOK_SECRET` and/or `GITHUB_WEBHOOK_SECRET` in `.env`, then
restart the stack. Point Linear at `https://<your-host>/webhooks/linear`
and GitHub at `https://<your-host>/webhooks/github`. Both require an HTTPS
reverse proxy in front of the bare 8000 port — use Caddy or Nginx; that's
out of scope for v0.1.

## Resetting

```bash
docker-compose down -v   # wipes gigabrain-data AND ollama-models volumes
```

## Where data lives

| Path inside container | Volume          | Contents                    |
|-----------------------|-----------------|-----------------------------|
| `/data/gigabrain.kuzu`         | `gigabrain-data` | Graph DB                   |
| `/data/gigabrain-vec.sqlite`   | `gigabrain-data` | Vector index               |
| `/data/traces/`                | `gigabrain-data` | OTel trace files           |
| `/root/.ollama/`               | `ollama-models`  | Embedding model weights    |

To back up: `docker run --rm -v gigabrain-data:/d -v $(pwd):/host alpine \
  tar czf /host/gigabrain-backup.tgz /d`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/self-hosting.md
git commit -m "docs(self-hosting): docker-compose install + Obsidian + backup"
```

---

## Task 6: Update root `README.md` to point at self-hosting

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Self-hosting" section near the top of `README.md`** (the engineer should find the right place — typically right after the project intro). The content:

```markdown
## Self-hosting

```bash
git clone https://github.com/kunggaochicken/GigaBrain.git
cd GigaBrain && cp .env.example .env
# edit .env to set ANTHROPIC_API_KEY
docker-compose up -d
open http://localhost:8000
```

See [`docs/self-hosting.md`](docs/self-hosting.md) for the full guide.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): link to docker-compose self-hosting guide"
```

---

## Task 7: CI smoke — does `docker-compose build` succeed?

**Files:**
- Create: `.github/workflows/docker-build.yml` (or modify existing CI if one exists)

- [ ] **Step 1: Check whether `.github/workflows/` exists and what's there**

```bash
ls .github/workflows/ 2>/dev/null
```

If there's already a CI workflow, add a job to it rather than creating a new file.

- [ ] **Step 2: Add a build job**

```yaml
# .github/workflows/docker-build.yml
name: docker-build

on:
  pull_request:
    paths:
      - 'Dockerfile'
      - 'docker-compose.yml'
      - 'backend/**'
      - 'frontend/**'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: docker-compose build
        run: docker compose build gigabrain
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docker-build.yml
git commit -m "ci(docker): build gigabrain image on PR"
```

---

## Task 8: Push and open the PR

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feat/plan-06-self-hosting
gh pr create --base main \
  --title "feat(docker): docker-compose self-hosting (Plan 06)" \
  --body "$(cat <<'EOF'
## Summary

- `Dockerfile` (multi-stage: node build + python runtime, serves frontend from `mount_frontend`).
- `docker-compose.yml` (gigabrain + ollama + init job).
- `.env.example` template.
- `backend/gigabrain.docker.yaml` (docker-mode config: `/data` paths, `http://ollama:11434`).
- `docs/self-hosting.md` (install, first capture, Obsidian mount, backup).
- README link to the self-hosting guide.
- CI: docker build runs on PRs that touch infrastructure files.

`docker-compose up` is now the one-command install for GigaBrain v0.1.

## Test plan

- [x] `docker-compose build` succeeds locally.
- [x] `docker-compose up -d` brings up healthy ollama, ollama-init exits 0, gigabrain responds on `/health`.
- [x] `POST /capture` writes a `Thought` and persists to `/data`.
- [x] `docker-compose down -v` cleans both named volumes.
EOF
)"
```

---

## Done — Plan 06 deliverable

After this PR merges, the v0.1 install story is one command:

```bash
git clone … && cd GigaBrain && cp .env.example .env && docker-compose up -d
```

That ends the v0.1 build. The remaining work is dogfood + v0.2 planning.
