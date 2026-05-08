from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.run_tests import RunTestsTool


@pytest.mark.asyncio
async def test_run_tests_invokes_configured_command(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    tool = RunTestsTool(command="pytest -q")
    ctx = ToolContext(
        agent_id="a", firing_id="f", vault_path=str(tmp_path / "v"), repo_path=str(repo)
    )

    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(return_value=(b"3 passed", b""))
    fake_proc.returncode = 0
    with patch(
        "asyncio.create_subprocess_shell", new=AsyncMock(return_value=fake_proc)
    ):
        out = await tool.run(ctx)
    assert "3 passed" in out


@pytest.mark.asyncio
async def test_run_tests_requires_repo_path(tmp_path: Path):
    tool = RunTestsTool(command="pytest")
    ctx = ToolContext(
        agent_id="a", firing_id="f", vault_path=str(tmp_path), repo_path=None
    )
    with pytest.raises(ValueError, match="no repo_path"):
        await tool.run(ctx)
