import subprocess
from pathlib import Path

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.stage_commits import StageCommitsTool


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)


@pytest.mark.asyncio
async def test_stage_and_commit_creates_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "f.py").write_text("x = 1\n")

    tool = StageCommitsTool()
    ctx = ToolContext(
        agent_id="a", firing_id="f", vault_path=str(tmp_path / "v"), repo_path=str(repo)
    )
    out = await tool.run(ctx, files=["f.py"], message="add f")
    assert "1 file changed" in out or "create mode" in out

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    )
    assert "add f" in log.stdout


@pytest.mark.asyncio
async def test_stage_commits_never_pushes(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "f.py").write_text("x = 1\n")

    push_called = []
    real_run = subprocess.run

    def _intercept(cmd, *args, **kwargs):
        if isinstance(cmd, list) and "push" in cmd:
            push_called.append(cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _intercept)

    tool = StageCommitsTool()
    ctx = ToolContext(
        agent_id="a", firing_id="f", vault_path=str(tmp_path / "v"), repo_path=str(repo)
    )
    await tool.run(ctx, files=["f.py"], message="add f")
    assert push_called == []
