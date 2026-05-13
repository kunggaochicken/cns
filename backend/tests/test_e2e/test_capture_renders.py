import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.embeddings.provider import EmbeddingsProvider


class StubEmbedder(EmbeddingsProvider):
    async def embed(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0, 0.0]

    @property
    def dim(self) -> int:
        return 4


@pytest.fixture
def test_app(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "gigabrain.yaml"
    cfg_path.write_text(f"""
db:
  kuzu_path: {tmp_path}/test.kuzu
  vector_path: {tmp_path}/test-vec.sqlite
embeddings:
  provider: ollama
  model: nomic-embed-text
  base_url: http://localhost:11434
llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY
telemetry:
  otlp_endpoint: file://{tmp_path}/traces
gigaflow:
  enabled: false
""")
    monkeypatch.setenv("GIGABRAIN_CONFIG", str(cfg_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key")

    from app import main as main_mod

    importlib.reload(main_mod)
    monkeypatch.setattr(main_mod, "build_provider", lambda _cfg: StubEmbedder())
    yield main_mod.app


def test_capture_thought_then_appears_in_graph_state(test_app):
    with TestClient(test_app) as client:
        pre = client.get("/graph/state").json()
        pre_count = sum(1 for n in pre["nodes"] if n["node_type"] == "thought")

        response = client.post(
            "/capture", json={"content": "smoke test", "source": "e2e"}
        )
        assert response.status_code == 200

        post = client.get("/graph/state").json()
        post_count = sum(1 for n in post["nodes"] if n["node_type"] == "thought")
        assert post_count == pre_count + 1
        assert any(
            n["node_type"] == "thought" and n["content"] == "smoke test"
            for n in post["nodes"]
        )
