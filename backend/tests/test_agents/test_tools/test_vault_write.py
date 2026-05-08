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


@pytest.mark.asyncio
async def test_write_rejects_sibling_prefix_traversal(tmp_path: Path):
    """A path like ../vault-secrets/file resolves to a sibling-prefixed dir
    that startswith() would accept but is outside the vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "vault-secrets").mkdir()

    tool = VaultWriteTool()
    ctx = ToolContext(agent_id="a", firing_id="f", vault_path=str(vault))
    with pytest.raises(ValueError, match="outside vault"):
        await tool.run(ctx, path="../vault-secrets/key", content="x")

    # Verify nothing got written to the sibling dir
    assert not (tmp_path / "vault-secrets" / "key").exists()
