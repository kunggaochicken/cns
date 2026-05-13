# GigaBrain CNS v2 — Plan 5: Obsidian Vault File-Watcher

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a background task in the FastAPI process that watches the Obsidian vault on disk (`agents.vault_path`) and captures every new or modified markdown file as a `thought` via the in-process capture pipeline. After this plan ships, a user who types a note into their vault has it instantly synapse-fired into the brain — no copy/paste, no CLI ritual.

**Architecture:** A single asyncio task subscribed to `watchfiles.awatch(vault_path)`. It buffers events per path, applies a configurable debounce window (default 2s), filters by an ignore-pattern list (default skips `.git/`, `.obsidian/`, `*.gigabrain*`), and reads-then-captures each stabilized markdown file. Capture is in-process via `normalize_and_persist` — no HTTP round trip. The watcher fails closed: if the vault path doesn't exist or `watchers.obsidian.enabled` is false, the task is not started and no error is raised.

**Tech Stack:** Python 3.11+, `watchfiles>=1.0` (already pulled in transitively by `uvicorn[standard]` — no new top-level dep). Standard-library `fnmatch` for the ignore patterns.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-gigabrain-cns-v2-design.md`](../specs/2026-05-06-gigabrain-cns-v2-design.md) §2 (Capture pipeline — Source adapters: "obsidian — file-watcher on the vault").

**Lessons from Plan 1–4 baked in:**
- Watching a path that doesn't exist must NOT crash the lifespan startup — gate behind `enabled` flag *and* a `Path.exists()` check.
- Default config paths must be writable without sudo; the vault is in `agents.vault_path` (already configured).
- `with TestClient(app) as client:` is required for lifespan to fire (so the watcher actually starts).
- Use `normalize_and_persist` directly inside the watcher — do NOT POST to `/capture` over HTTP from the same process.
- `watchfiles.awatch` is an async generator; cancel its task on shutdown by holding the `asyncio.Task` and `task.cancel()` in the lifespan's teardown.
- File reads should silently skip empty files and binary content (the watcher only fires on markdown via the suffix filter, so binary is unlikely, but defend against it anyway).
- Add `watchers.obsidian.enabled = false` to `gigabrain.yaml.example` so a first-time user doesn't fire the watcher with a wrong path.

---

## Scope: 1 PR, ~10 tasks

This plan is one focused PR — `feat/plan-05-obsidian-watcher` — branching off `main` after Plan 04 lands. The file-watcher is a single component with three internal seams (path filter, debouncer, orchestrator) that we test independently before wiring.

---

## File structure

```
backend/
└── app/
    ├── watchers/
    │   ├── __init__.py
    │   ├── obsidian.py             # The watcher (filter + debouncer + orchestrator)
    │   └── debounce.py             # Pure debounce helper, separately testable
    └── config.py                   # Add WatchersConfig + ObsidianWatcherConfig

tests/
└── test_watchers/
    ├── __init__.py
    ├── test_debounce.py            # Debouncer in isolation
    ├── test_obsidian_filter.py     # Path-ignore filter
    ├── test_obsidian_watcher.py    # Orchestrator with watchfiles stubbed
    └── test_e2e_real_vault.py      # Real tmp_path + real watchfiles, single iteration
```

---

## Task 1: Add `WatchersConfig` and `ObsidianWatcherConfig`

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/gigabrain.yaml.example`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_config.py`:

```python
def test_loads_watchers_obsidian_section(tmp_path):
    from app.config import load_config

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text(
        "watchers:\n"
        "  obsidian:\n"
        "    enabled: true\n"
        "    debounce_seconds: 1.5\n"
        "    ignore_patterns:\n"
        "      - .git/*\n"
        "      - .obsidian/*\n"
    )
    cfg = load_config(cfg_path)
    assert cfg.watchers.obsidian.enabled is True
    assert cfg.watchers.obsidian.debounce_seconds == 1.5
    assert cfg.watchers.obsidian.ignore_patterns == [".git/*", ".obsidian/*"]


def test_watchers_obsidian_defaults():
    from app.config import GigaBrainConfig

    cfg = GigaBrainConfig()
    assert cfg.watchers.obsidian.enabled is False
    assert cfg.watchers.obsidian.debounce_seconds == 2.0
    assert ".git/*" in cfg.watchers.obsidian.ignore_patterns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_config.py -v -k watchers`
Expected: FAIL — `cfg.watchers` doesn't exist.

- [ ] **Step 3: Add the config classes**

In `backend/app/config.py`, add (place near `AgentsConfig`):

```python
class ObsidianWatcherConfig(BaseModel):
    enabled: bool = False
    debounce_seconds: float = 2.0
    ignore_patterns: list[str] = [
        ".git/*",
        ".obsidian/*",
        "*.gigabrain*",
    ]


class WatchersConfig(BaseModel):
    obsidian: ObsidianWatcherConfig = ObsidianWatcherConfig()
```

Wire into `GigaBrainConfig`:

```python
class GigaBrainConfig(BaseModel):
    db: DBConfig = DBConfig()
    embeddings: EmbeddingsConfig = EmbeddingsConfig()
    llm: LLMConfig = LLMConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    gigaflow: GigaFlowConfig = GigaFlowConfig()
    agents: AgentsConfig = AgentsConfig()
    capture: CaptureClientConfig = CaptureClientConfig()
    webhooks: WebhooksConfig = WebhooksConfig()
    watchers: WatchersConfig = WatchersConfig()
```

- [ ] **Step 4: Update `gigabrain.yaml.example`**

Append:

```yaml
watchers:
  obsidian:
    # Set enabled: true once agents.vault_path points at a real vault.
    enabled: false
    debounce_seconds: 2.0
    ignore_patterns:
      - .git/*
      - .obsidian/*
      - "*.gigabrain*"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/gigabrain.yaml.example backend/tests/test_config.py
git commit -m "feat(config): add WatchersConfig.obsidian section

Foundation for Plan 05's file-watcher. Default enabled=false so first-time
users do not accidentally fire the watcher against a wrong path."
```

---

## Task 2: Path-filter — write failing tests

**Files:**
- Create: `backend/tests/test_watchers/__init__.py` (empty)
- Create: `backend/tests/test_watchers/test_obsidian_filter.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_watchers/test_obsidian_filter.py
from pathlib import Path

from app.watchers.obsidian import should_capture


def test_includes_markdown_in_vault_root():
    assert should_capture(
        vault=Path("/v"),
        path=Path("/v/note.md"),
        ignore_patterns=[".git/*", ".obsidian/*"],
    )


def test_includes_markdown_in_subdir():
    assert should_capture(
        vault=Path("/v"),
        path=Path("/v/Brain/Bets/bet_x.md"),
        ignore_patterns=[".git/*", ".obsidian/*"],
    )


def test_skips_non_markdown():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/picture.png"),
        ignore_patterns=[".git/*", ".obsidian/*"],
    )


def test_skips_paths_outside_vault():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/elsewhere/note.md"),
        ignore_patterns=[],
    )


def test_skips_ignored_dotdir_patterns():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/.git/HEAD"),
        ignore_patterns=[".git/*"],
    )
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/.obsidian/workspace.json"),
        ignore_patterns=[".obsidian/*"],
    )


def test_skips_gigabrain_metadata_files():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/Brain/.gigabrain-state.md"),
        ignore_patterns=["*.gigabrain*"],
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_watchers/test_obsidian_filter.py -v`
Expected: FAIL — module doesn't exist.

---

## Task 3: Implement `should_capture`

**Files:**
- Create: `backend/app/watchers/__init__.py` (empty)
- Create: `backend/app/watchers/obsidian.py` (start with the filter helper only)

- [ ] **Step 1: Write the implementation**

```python
# backend/app/watchers/obsidian.py
import fnmatch
from pathlib import Path


def should_capture(
    *,
    vault: Path,
    path: Path,
    ignore_patterns: list[str],
) -> bool:
    """Return True if `path` is a markdown file inside `vault` that does not
    match any of `ignore_patterns` (fnmatch against the vault-relative path).
    """
    vault = vault.resolve()
    try:
        rel = path.resolve().relative_to(vault)
    except ValueError:
        return False
    if path.suffix.lower() != ".md":
        return False
    rel_str = str(rel)
    for pat in ignore_patterns:
        if fnmatch.fnmatch(rel_str, pat):
            return False
        # Also match any path component (e.g. ".git/*" against "Notes/.git/x.md").
        for part in rel.parts:
            if fnmatch.fnmatch(part, pat.rstrip("/*")):
                return False
    return True
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_watchers/test_obsidian_filter.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 3: Commit**

```bash
git add backend/app/watchers/__init__.py backend/app/watchers/obsidian.py \
        backend/tests/test_watchers/__init__.py backend/tests/test_watchers/test_obsidian_filter.py
git commit -m "feat(watchers): obsidian path filter (.md inside vault, fnmatch ignore)"
```

---

## Task 4: Debouncer — write failing tests

**Files:**
- Create: `backend/tests/test_watchers/test_debounce.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_watchers/test_debounce.py
import asyncio
import time

import pytest

from app.watchers.debounce import PerPathDebouncer


@pytest.mark.asyncio
async def test_emits_after_quiet_window():
    db = PerPathDebouncer(window_seconds=0.05)
    emitted: list[str] = []

    async def collect():
        async for path in db.stream():
            emitted.append(path)

    task = asyncio.create_task(collect())
    db.push("/v/a.md")
    await asyncio.sleep(0.1)
    db.close()
    await task
    assert emitted == ["/v/a.md"]


@pytest.mark.asyncio
async def test_coalesces_rapid_writes():
    db = PerPathDebouncer(window_seconds=0.05)
    emitted: list[str] = []

    async def collect():
        async for path in db.stream():
            emitted.append(path)

    task = asyncio.create_task(collect())
    for _ in range(10):
        db.push("/v/a.md")
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.1)
    db.close()
    await task
    assert emitted == ["/v/a.md"]


@pytest.mark.asyncio
async def test_independent_paths_emit_independently():
    db = PerPathDebouncer(window_seconds=0.05)
    emitted: list[str] = []

    async def collect():
        async for path in db.stream():
            emitted.append(path)

    task = asyncio.create_task(collect())
    db.push("/v/a.md")
    db.push("/v/b.md")
    await asyncio.sleep(0.1)
    db.close()
    await task
    assert sorted(emitted) == ["/v/a.md", "/v/b.md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_watchers/test_debounce.py -v`
Expected: FAIL — module doesn't exist.

---

## Task 5: Implement `PerPathDebouncer`

**Files:**
- Create: `backend/app/watchers/debounce.py`

- [ ] **Step 1: Write the implementation**

```python
# backend/app/watchers/debounce.py
import asyncio
import time
from collections.abc import AsyncIterator


class PerPathDebouncer:
    """Coalesces rapid pushes per path; emits each path once after `window_seconds`
    elapse with no further pushes for that path.

    Single-consumer: only one call to `stream()` is supported at a time.
    """

    def __init__(self, window_seconds: float):
        self._window = window_seconds
        self._last: dict[str, float] = {}
        self._wake = asyncio.Event()
        self._closed = False

    def push(self, path: str) -> None:
        self._last[path] = time.monotonic()
        self._wake.set()

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    async def stream(self) -> AsyncIterator[str]:
        while not self._closed or self._last:
            if not self._last:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self._window)
                except asyncio.TimeoutError:
                    pass
                continue
            now = time.monotonic()
            ready = [p for p, t in self._last.items() if now - t >= self._window]
            if ready:
                for p in ready:
                    del self._last[p]
                    yield p
                continue
            # Sleep until the oldest entry will be ready (or until a new push arrives).
            soonest = min(self._last.values())
            wait = max(0.0, (soonest + self._window) - now)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_watchers/test_debounce.py -v`
Expected: PASS — all 3 tests.

- [ ] **Step 3: Commit**

```bash
git add backend/app/watchers/debounce.py backend/tests/test_watchers/test_debounce.py
git commit -m "feat(watchers): per-path debouncer (asyncio, single consumer)"
```

---

## Task 6: Orchestrator — write failing tests

**Files:**
- Create: `backend/tests/test_watchers/test_obsidian_watcher.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_watchers/test_obsidian_watcher.py
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus
from app.watchers.obsidian import ObsidianWatcher


@pytest.mark.asyncio
async def test_captures_new_markdown_file(tmp_path: Path):
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

    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "first.md"
    note.write_text("# First note\n\nHello, brain.")

    watcher = ObsidianWatcher(
        vault=vault,
        nodes=nodes,
        vec=vec,
        bus=bus,
        embedder=embedder,
        debounce_seconds=0.05,
        ignore_patterns=[],
    )
    # Drive a single synthetic event through the orchestrator's path handler
    # (this avoids depending on the real filesystem watcher for unit tests).
    await watcher._handle_path(note)

    rows = conn.query("MATCH (t:Thought) RETURN t.source AS source, t.content AS content")
    assert len(rows) == 1
    assert rows[0]["source"] == "obsidian"
    assert "Hello, brain" in rows[0]["content"]

    vec.close()
    conn.close()


@pytest.mark.asyncio
async def test_skips_ignored_path(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".git").mkdir()
    bad = vault / ".git" / "HEAD"
    bad.write_text("ref: refs/heads/main")

    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]

    watcher = ObsidianWatcher(
        vault=vault,
        nodes=nodes,
        vec=vec,
        bus=EventBus(),
        embedder=embedder,
        debounce_seconds=0.05,
        ignore_patterns=[".git/*"],
    )
    await watcher._handle_path(bad)

    rows = conn.query("MATCH (t:Thought) RETURN t.id")
    assert rows == []
    vec.close()
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_watchers/test_obsidian_watcher.py -v`
Expected: FAIL — `ObsidianWatcher` doesn't exist.

---

## Task 7: Implement `ObsidianWatcher` orchestrator

**Files:**
- Modify: `backend/app/watchers/obsidian.py` (append the class)

- [ ] **Step 1: Append the implementation**

Add to `backend/app/watchers/obsidian.py`:

```python
import asyncio
import logging
from dataclasses import dataclass

from watchfiles import Change, awatch

from app.capture.normalizer import normalize_and_persist
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus
from app.watchers.debounce import PerPathDebouncer

log = logging.getLogger(__name__)


@dataclass
class ObsidianWatcher:
    vault: Path
    nodes: NodeRepository
    vec: VectorStore
    bus: EventBus
    embedder: EmbeddingsProvider
    debounce_seconds: float
    ignore_patterns: list[str]

    async def run(self) -> None:
        """Long-running task. Cancel to stop."""
        if not self.vault.exists():
            log.warning("Obsidian watcher: vault path %s does not exist; not starting", self.vault)
            return

        debouncer = PerPathDebouncer(window_seconds=self.debounce_seconds)

        async def emit_loop():
            async for path_str in debouncer.stream():
                try:
                    await self._handle_path(Path(path_str))
                except Exception:
                    log.exception("Obsidian watcher: failed to capture %s", path_str)

        emit_task = asyncio.create_task(emit_loop())
        try:
            async for changes in awatch(str(self.vault)):
                for change_type, raw_path in changes:
                    if change_type == Change.deleted:
                        continue
                    debouncer.push(raw_path)
        finally:
            debouncer.close()
            await emit_task

    async def _handle_path(self, path: Path) -> None:
        if not should_capture(
            vault=self.vault,
            path=path,
            ignore_patterns=self.ignore_patterns,
        ):
            return
        try:
            content = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            return
        if not content.strip():
            return
        rel = path.resolve().relative_to(self.vault.resolve())
        await normalize_and_persist(
            content=content,
            source="obsidian",
            metadata={"vault_path": str(rel)},
            nodes=self.nodes,
            vec=self.vec,
            bus=self.bus,
            embedder=self.embedder,
        )
```

(The `Path` import already exists at the top of the file from Task 3 — confirm before adding a duplicate.)

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_watchers/ -v`
Expected: PASS — filter tests still pass, debounce tests still pass, new watcher tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/watchers/obsidian.py backend/tests/test_watchers/test_obsidian_watcher.py
git commit -m "feat(watchers): ObsidianWatcher orchestrator (watchfiles + debouncer)"
```

---

## Task 8: Wire watcher into `main.py` lifespan

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_main_lifespan.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_main_lifespan.py`:

```python
def test_obsidian_watcher_starts_when_enabled(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    cfg = tmp_path / "g.yaml"
    cfg.write_text(
        f"db:\n"
        f"  kuzu_path: {tmp_path}/k.kuzu\n"
        f"  vector_path: {tmp_path}/v.sqlite\n"
        f"agents:\n"
        f"  vault_path: {vault}\n"
        f"watchers:\n"
        f"  obsidian:\n"
        f"    enabled: true\n"
        f"    debounce_seconds: 0.05\n"
    )
    monkeypatch.setenv("GIGABRAIN_CONFIG", str(cfg))

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        # Watcher task should be registered on app.state.
        assert hasattr(app.state, "obsidian_watcher_task")
        assert app.state.obsidian_watcher_task is not None
        # On teardown, the task should be cancelled cleanly (no warnings).


def test_obsidian_watcher_not_started_when_disabled(monkeypatch, tmp_path):
    cfg = tmp_path / "g.yaml"
    cfg.write_text(
        f"db:\n"
        f"  kuzu_path: {tmp_path}/k.kuzu\n"
        f"  vector_path: {tmp_path}/v.sqlite\n"
    )
    monkeypatch.setenv("GIGABRAIN_CONFIG", str(cfg))

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        assert getattr(app.state, "obsidian_watcher_task", None) is None
```

- [ ] **Step 2: Run test**

Run: `cd backend && uv run python -m pytest tests/test_main_lifespan.py -v -k obsidian`
Expected: FAIL — `app.state.obsidian_watcher_task` doesn't exist.

- [ ] **Step 3: Wire it up**

In `backend/app/main.py`, inside `lifespan()`, after the agent worker is attached but before `yield`, add:

```python
    from app.watchers.obsidian import ObsidianWatcher

    obsidian_cfg = cfg.watchers.obsidian
    if obsidian_cfg.enabled and Path(cfg.agents.vault_path).exists():
        watcher = ObsidianWatcher(
            vault=Path(cfg.agents.vault_path),
            nodes=nodes,
            vec=vec,
            bus=bus,
            embedder=embedder,
            debounce_seconds=obsidian_cfg.debounce_seconds,
            ignore_patterns=obsidian_cfg.ignore_patterns,
        )
        app.state.obsidian_watcher_task = asyncio.create_task(watcher.run())
    else:
        app.state.obsidian_watcher_task = None
```

And in the teardown section (after `yield`):

```python
    if app.state.obsidian_watcher_task is not None:
        app.state.obsidian_watcher_task.cancel()
        try:
            await app.state.obsidian_watcher_task
        except (asyncio.CancelledError, Exception):
            pass
```

Add `import asyncio` to the top of the file if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_main_lifespan.py -v`
Expected: PASS — including the two new watcher tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_main_lifespan.py
git commit -m "feat(main): start ObsidianWatcher background task when enabled

Watcher only starts if both watchers.obsidian.enabled is true AND the vault
path exists. Cancelled cleanly on lifespan teardown."
```

---

## Task 9: E2E — real filesystem write triggers a thought

**Files:**
- Create: `backend/tests/test_watchers/test_e2e_real_vault.py`

This test uses the real `watchfiles` (not a mock) against a `tmp_path` vault. It writes a file, waits a beat for the watcher to fire, asserts a `Thought` node appears. It can be flaky on slow CI — mark `@pytest.mark.slow` if a marker exists; if not, just keep the wait generous.

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_watchers/test_e2e_real_vault.py
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus
from app.watchers.obsidian import ObsidianWatcher


@pytest.mark.asyncio
async def test_real_filesystem_write_captures_thought(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()

    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]

    watcher = ObsidianWatcher(
        vault=vault,
        nodes=nodes,
        vec=vec,
        bus=EventBus(),
        embedder=embedder,
        debounce_seconds=0.1,
        ignore_patterns=[],
    )

    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.sleep(0.2)  # let the watcher start
        (vault / "note.md").write_text("# Real write\n\nSynapse fired.")
        # Wait up to 5s for the thought to land
        for _ in range(50):
            await asyncio.sleep(0.1)
            rows = conn.query("MATCH (t:Thought) RETURN t.content AS content")
            if rows:
                break
        assert rows, "expected a Thought row after the file write"
        assert "Synapse fired" in rows[0]["content"]
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        vec.close()
        conn.close()
```

- [ ] **Step 2: Run test**

Run: `cd backend && uv run python -m pytest tests/test_watchers/test_e2e_real_vault.py -v`
Expected: PASS (may take 1–5s).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_watchers/test_e2e_real_vault.py
git commit -m "test(watchers): real-filesystem E2E for obsidian watcher"
```

---

## Task 10: Push and open the PR

- [ ] **Step 1: Push the branch and open PR**

```bash
git push -u origin feat/plan-05-obsidian-watcher
gh pr create --base main \
  --title "feat(watchers): Obsidian vault file-watcher (Plan 05)" \
  --body "$(cat <<'EOF'
## Summary

- New `ObsidianWatcher` background task that captures `.md` writes inside the configured vault as thoughts (source: `obsidian`).
- Configurable via `watchers.obsidian.{enabled, debounce_seconds, ignore_patterns}` — disabled by default, ignores `.git/`, `.obsidian/`, and `*.gigabrain*` by default.
- Watcher fails closed: skips if vault path doesn't exist; cancels cleanly on lifespan teardown.

## Test plan

- [x] Unit tests for the path filter (6 cases).
- [x] Unit tests for the debouncer (3 cases — single emit, coalescing, independence per path).
- [x] Orchestrator unit tests with synthetic events.
- [x] Lifespan tests for enabled/disabled wiring.
- [x] E2E test against a real `tmp_path` vault with the real `watchfiles` library.
EOF
)"
```

---

## Done — Plan 05 deliverable

After this PR merges, a user can:

1. Set `agents.vault_path` to their Obsidian vault.
2. Flip `watchers.obsidian.enabled: true` in `gigabrain.yaml`.
3. Restart the backend.
4. Edit a `.md` file in the vault → a `thought` lands in the brain within `debounce_seconds`, gets embedded, gets sparred, and shows up in the brain view in real time.

This completes the v0.1 source-adapter list. The last v0.1 deliverable is docker-compose self-hosting (Plan 06).
