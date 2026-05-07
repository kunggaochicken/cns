import os
from unittest.mock import AsyncMock, patch

import pytest
from app.config import LLMConfig
from app.sparring.llm import SparringResult, run_spar


@pytest.mark.asyncio
async def test_run_spar_returns_structured_result():
    cfg = LLMConfig(provider="anthropic", model="claude-sonnet-4-6", api_key_env="X")
    mock_result = SparringResult(
        classification="conflict",
        reasoning="Contradicts bet b_auth",
        edges_to_record=[
            {"target_id": "b_auth", "edge_type": "contradicts", "confidence": 0.9}
        ],
        suggested_action=None,
    )
    with (
        patch.dict(os.environ, {"X": "test-key"}),
        patch("app.sparring.llm.Agent") as MockAgent,  # noqa: N806
    ):
        instance = MockAgent.return_value
        instance.run = AsyncMock(return_value=type("R", (), {"output": mock_result})())
        result = await run_spar(
            cfg=cfg,
            thought_content="we should drop oauth",
            context_bundle={"nodes": [{"id": "b_auth", "table": "Bet"}], "edges": []},
        )
    assert result.classification == "conflict"
    assert result.edges_to_record[0].target_id == "b_auth"
