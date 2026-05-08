import os
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from app.config import LLMConfig
from app.sparring.prompts import SPARRING_SYSTEM_PROMPT, build_user_message


class SparringEdge(BaseModel):
    target_id: str
    edge_type: Literal[
        "sparred-against", "contradicts", "aligns-with", "supersedes", "related-to"
    ]
    confidence: float


class SuggestedAction(BaseModel):
    agent_role: Literal["engineer", "writer", "pm", "cto", "inbox"]
    task_summary: str


class SparringResult(BaseModel):
    classification: Literal["clear", "conflict", "novel"]
    reasoning: str
    edges_to_record: list[SparringEdge] = []
    suggested_action: SuggestedAction | None = None


def _build_agent(cfg: LLMConfig) -> Agent:
    api_key = os.environ.get(cfg.api_key_env, "")
    if cfg.provider == "anthropic":
        provider = AnthropicProvider(api_key=api_key or None)
        model = AnthropicModel(cfg.model, provider=provider)
    else:
        raise ValueError(f"Unsupported LLM provider for sparring: {cfg.provider}")
    return Agent(
        model=model, system_prompt=SPARRING_SYSTEM_PROMPT, output_type=SparringResult
    )


async def run_spar(
    *,
    cfg: LLMConfig,
    thought_content: str,
    context_bundle: dict,
) -> SparringResult:
    agent = _build_agent(cfg)
    user_msg = build_user_message(thought_content, context_bundle)
    result = await agent.run(user_msg)
    return result.output
