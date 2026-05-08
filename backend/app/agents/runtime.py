import os

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from app.agents.config import AgentSpec
from app.agents.prompts import build_system_prompt
from app.agents.tools.base import GLOBAL_REVERSIBLE_INTERNAL
from app.config import LLMConfig


class AgentAction(BaseModel):
    """One concrete action the agent took during a run."""

    tool: str
    summary: str


class AgentRunResult(BaseModel):
    """Structured output from an agent run."""

    summary: str
    actions_taken: list[AgentAction] = []


class AgentRuntime:
    def __init__(
        self,
        *,
        spec: AgentSpec,
        llm_cfg: LLMConfig,
        vault_path: str,
        repo_path: str | None,
    ):
        # Pre-flight: every tool the agent declares must be in the global fence
        for tool_name in spec.tools:
            if tool_name not in GLOBAL_REVERSIBLE_INTERNAL:
                raise ValueError(
                    f"Tool {tool_name!r} declared by agent {spec.id!r} "
                    f"is not in global reversible-internal fence"
                )
        self.spec = spec
        self.vault_path = vault_path
        self.repo_path = repo_path

        api_key = os.environ.get(llm_cfg.api_key_env, "") or None
        if llm_cfg.provider != "anthropic":
            raise ValueError(f"Unsupported LLM provider for agents: {llm_cfg.provider}")
        model = AnthropicModel(
            llm_cfg.model,
            provider=AnthropicProvider(api_key=api_key),
        )
        system_prompt = build_system_prompt(spec.role, spec.persona)
        self._agent: Agent[None, AgentRunResult] = Agent(
            model=model,
            system_prompt=system_prompt,
            output_type=AgentRunResult,
        )
        # Tool registration deferred to v0.2 — pydantic-ai 1.x tool API differs
        # across minors. v0.1 ships agents that produce structured summaries.

    async def run(self, *, firing_id: str, task_summary: str) -> AgentRunResult:
        user_msg = f"Task (firing_id={firing_id}):\n{task_summary}"
        result = await self._agent.run(user_msg)
        return result.output
