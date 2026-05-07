from unittest.mock import patch

import pytest
from app.config import EmbeddingsConfig
from app.embeddings.factory import build_provider
from app.embeddings.ollama import OllamaEmbedder


def test_factory_returns_ollama_provider():
    cfg = EmbeddingsConfig(provider="ollama", model="nomic-embed-text")
    provider = build_provider(cfg)
    assert isinstance(provider, OllamaEmbedder)


@pytest.mark.asyncio
async def test_ollama_embedder_calls_api():
    cfg = EmbeddingsConfig(
        provider="ollama", model="nomic-embed-text", base_url="http://localhost:11434"
    )
    embedder = OllamaEmbedder(cfg)
    fake_response = {"embedding": [0.1] * 768}
    with patch("ollama.AsyncClient") as MockClient:  # noqa: N806
        instance = MockClient.return_value

        async def fake_embeddings(**kwargs):
            return fake_response

        instance.embeddings = fake_embeddings
        vec = await embedder.embed("hello world")
    assert len(vec) == 768
    assert vec[0] == 0.1
