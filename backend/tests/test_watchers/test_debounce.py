import asyncio

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
