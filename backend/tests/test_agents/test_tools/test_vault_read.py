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
