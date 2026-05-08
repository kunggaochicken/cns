import os
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.config import AgentSpec
from app.agents.runtime import AgentRunResult, AgentRuntime
from app.config import LLMConfig


@pytest.mark.asyncio
async def test_runtime_runs_agent_and_returns_output():
    spec = AgentSpec(
        id="eng-1", role="engineer", persona="drafts code", tools=["vault_read"]
    )
    cfg = LLMConfig(
        provider="anthropic", model="claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY"
    )

    mock_output = AgentRunResult(summary="drafted thing", actions_taken=[])
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("app.agents.runtime.Agent") as MockAgent:  # noqa: N806
            instance = MockAgent.return_value
            instance.run = AsyncMock(
                return_value=type("R", (), {"output": mock_output})()
            )
            runtime = AgentRuntime(
                spec=spec,
                llm_cfg=cfg,
                vault_path="/tmp/vault",
                repo_path=None,
            )
            out = await runtime.run(firing_id="f_1", task_summary="add /capture")

    assert out.summary == "drafted thing"


@pytest.mark.asyncio
async def test_runtime_rejects_tool_outside_global_fence():
    # send_email is not in GLOBAL_REVERSIBLE_INTERNAL — runtime should reject at construction
    # We use Pydantic to bypass the AgentSpec Literal validator (which would reject
    # send_email at config time). Construct an AgentSpec via dict-construction trick:
    spec = AgentSpec.model_construct(
        id="eng-1",
        role="engineer",
        persona="x",
        enabled=True,
        tools=["send_email"],
        escalates_to=None,
    )
    cfg = LLMConfig(provider="anthropic", model="x", api_key_env="X")
    with patch.dict(os.environ, {"X": "test-key"}):
        with patch("app.agents.runtime.Agent"):
            with pytest.raises(
                ValueError, match="not in global reversible-internal fence"
            ):
                AgentRuntime(
                    spec=spec,
                    llm_cfg=cfg,
                    vault_path="/tmp/vault",
                    repo_path=None,
                )
