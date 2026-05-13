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
    with TestClient(configured_app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200


def test_capture_route_is_mounted(configured_app):
    with TestClient(configured_app) as client:
        resp = client.post("/capture", json={"content": "hi", "source": "cli"})
        # Either succeeds (Ollama up) or 5xx (Ollama down); both confirm the route exists.
        assert resp.status_code in (200, 500, 502, 503)


def test_github_webhook_mounted_when_secret_env_set(monkeypatch, tmp_path):
    monkeypatch.setenv("GH_WEBHOOK_SECRET", "test-secret")

    cfg = tmp_path / "g.yaml"
    cfg.write_text(
        f"db:\n"
        f"  kuzu_path: {tmp_path}/k.kuzu\n"
        f"  vector_path: {tmp_path}/v.sqlite\n"
        f"webhooks:\n"
        f"  github_secret_env: GH_WEBHOOK_SECRET\n"
    )
    monkeypatch.setenv("GIGABRAIN_CONFIG", str(cfg))

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github", content=b"{}", headers={"x-github-event": "ping"}
        )
        assert r.status_code == 401
