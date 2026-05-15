import os
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from app.config import LLMConfig


class DuplicateVerdict(BaseModel):
    relation: Literal["same", "near", "different"]
    reasoning: str
    confidence: float


class ConflictVerdict(BaseModel):
    contradicts: bool
    summary: str  # one-sentence statement of the contradiction
    reasoning: str
    confidence: float


_DUPLICATE_PROMPT = (
    "You are a duplicate-detection brainstem. Given THOUGHT_A and THOUGHT_B, "
    "decide whether they are: 'same' (a verbatim or trivially-rephrased restatement), "
    "'near' (substantively the same idea but a meaningful rewrite or extension), "
    "or 'different' (distinct ideas that merely share vocabulary). "
    "Be conservative: prefer 'different' unless the overlap is clear. "
    "Output JSON only."
)


_CONFLICT_PROMPT = (
    "You are a dialectic detector. Given a NEW THOUGHT and a CANDIDATE prior thought, "
    "decide whether the new thought CONTRADICTS the candidate — i.e. asserts the "
    "opposite, undermines its premise, or proposes a direction incompatible with it. "
    "Tension or disagreement counts. Topical similarity alone does NOT. "
    "Output JSON only."
)


def _resolve_api_key(env_var: str) -> str:
    # Fall back to a placeholder so the provider can be constructed in tests /
    # offline contexts. Real calls will fail at request time without a valid key,
    # which is the desired behavior.
    return (
        os.environ.get(env_var)
        or os.environ.get("ANTHROPIC_API_KEY")
        or "missing-api-key"
    )


def build_duplicate_agent(api_key_env: str = "ANTHROPIC_API_KEY") -> Agent:
    provider = AnthropicProvider(api_key=_resolve_api_key(api_key_env))
    model = AnthropicModel("claude-haiku-4-5-20251001", provider=provider)
    return Agent(
        model=model, system_prompt=_DUPLICATE_PROMPT, output_type=DuplicateVerdict
    )


def build_conflict_agent(cfg: LLMConfig) -> Agent:
    provider = AnthropicProvider(api_key=_resolve_api_key(cfg.api_key_env))
    # Use the config-supplied model (project default: claude-sonnet-4-6)
    model = AnthropicModel(cfg.model, provider=provider)
    return Agent(
        model=model, system_prompt=_CONFLICT_PROMPT, output_type=ConflictVerdict
    )


def duplicate_user_message(a: str, b: str) -> str:
    return f"THOUGHT_A:\n{a}\n\nTHOUGHT_B:\n{b}\n\nClassify and emit JSON."


def conflict_user_message(new_thought: str, candidate: str) -> str:
    return (
        f"NEW THOUGHT:\n{new_thought}\n\n"
        f"CANDIDATE PRIOR THOUGHT:\n{candidate}\n\n"
        "Does the new thought contradict the candidate? Emit JSON."
    )
