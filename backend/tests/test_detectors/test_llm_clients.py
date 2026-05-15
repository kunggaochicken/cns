from app.config import LLMConfig
from app.detectors.llm_clients import (
    build_conflict_agent,
    build_duplicate_agent,
    conflict_user_message,
    duplicate_user_message,
)


def test_duplicate_agent_constructs():
    agent = build_duplicate_agent(api_key_env="UNSET_ENV_VAR_OK")
    assert agent is not None


def test_conflict_agent_uses_config_model():
    cfg = LLMConfig(
        provider="anthropic", model="claude-sonnet-4-6", api_key_env="UNSET"
    )
    agent = build_conflict_agent(cfg)
    assert agent is not None


def test_duplicate_user_message_includes_both_thoughts():
    msg = duplicate_user_message("alpha thing", "beta thing")
    assert "alpha thing" in msg
    assert "beta thing" in msg


def test_conflict_user_message_includes_both():
    msg = conflict_user_message("we should ship preview", "we agreed to delay preview")
    assert "we should ship preview" in msg
    assert "we agreed to delay preview" in msg
