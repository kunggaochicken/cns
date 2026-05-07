from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def configured_app(tmp_path: Path, monkeypatch):
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
    import importlib
    from app import main

    importlib.reload(main)
    yield main.app


def test_health_works_with_full_lifespan(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_capture_route_is_mounted(configured_app):
    client = TestClient(configured_app)
    # Either succeeds (Ollama up) or 5xx (Ollama down); both confirm the route exists.
    resp = client.post("/capture", json={"content": "hi", "source": "cli"})
    assert resp.status_code in (200, 500, 502, 503)
