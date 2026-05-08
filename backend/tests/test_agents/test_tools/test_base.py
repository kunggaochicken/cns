import pytest

from app.agents.tools.base import (
    FenceDeniedError,
    GLOBAL_REVERSIBLE_INTERNAL,
    Tool,
    ToolContext,
    enforce_fence,
)


class _DummyTool(Tool):
    name = "dummy_safe"

    async def run(self, ctx: ToolContext, **kwargs) -> str:
        return "ok"


class _DummyExternal(Tool):
    name = "send_email"

    async def run(self, ctx: ToolContext, **kwargs) -> str:
        return "should not run"


def test_global_fence_lists_internal_tools_only():
    assert "vault_read" in GLOBAL_REVERSIBLE_INTERNAL
    assert "vault_write" in GLOBAL_REVERSIBLE_INTERNAL
    assert "run_tests" in GLOBAL_REVERSIBLE_INTERNAL
    assert "stage_commits" in GLOBAL_REVERSIBLE_INTERNAL
    assert "send_email" not in GLOBAL_REVERSIBLE_INTERNAL


def test_enforce_fence_passes_when_in_global_and_in_agent_allowlist():
    enforce_fence(tool_name="vault_write", agent_allowlist=["vault_write", "run_tests"])


def test_enforce_fence_denies_outside_global():
    with pytest.raises(
        FenceDeniedError, match="not in global reversible-internal fence"
    ):
        enforce_fence(tool_name="send_email", agent_allowlist=["send_email"])


def test_enforce_fence_denies_outside_agent_allowlist():
    with pytest.raises(FenceDeniedError, match="not in agent's allowlist"):
        enforce_fence(tool_name="run_tests", agent_allowlist=["vault_read"])
