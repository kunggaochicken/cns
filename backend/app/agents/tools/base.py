from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass


GLOBAL_REVERSIBLE_INTERNAL: frozenset[str] = frozenset(
    {
        "vault_read",
        "vault_write",
        "run_tests",
        "stage_commits",
        "linear_read",
        "github_read",
    }
)


class FenceDeniedError(RuntimeError):
    """Raised when a tool call is outside the fence (global or agent-level)."""


@dataclass
class ToolContext:
    agent_id: str
    firing_id: str
    vault_path: str
    repo_path: str | None = None


class Tool(ABC):
    name: str

    @abstractmethod
    async def run(self, ctx: ToolContext, **kwargs) -> str: ...


def enforce_fence(*, tool_name: str, agent_allowlist: Iterable[str]) -> None:
    if tool_name not in GLOBAL_REVERSIBLE_INTERNAL:
        raise FenceDeniedError(
            f"Tool {tool_name!r} not in global reversible-internal fence"
        )
    if tool_name not in agent_allowlist:
        raise FenceDeniedError(
            f"Tool {tool_name!r} not in agent's allowlist {list(agent_allowlist)!r}"
        )
