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
    rows: list = []
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
