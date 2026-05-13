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

    rows = conn.query(
        "MATCH (t:Thought) RETURN t.source AS source, t.content AS content"
    )
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
