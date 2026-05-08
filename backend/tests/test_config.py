from pathlib import Path

import pytest
from app.config import load_config


def test_load_config_from_yaml(tmp_path: Path):
    cfg_file = tmp_path / "gigabrain.yaml"
    cfg_file.write_text(
        """
db:
  kuzu_path: /tmp/test.kuzu
  vector_path: /tmp/test-vec.sqlite

embeddings:
  provider: ollama
  model: nomic-embed-text
  base_url: http://localhost:11434

llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY

telemetry:
  otlp_endpoint: file:///tmp/traces

gigaflow:
  enabled: false
        """
    )
    cfg = load_config(cfg_file)
    assert cfg.db.kuzu_path == "/tmp/test.kuzu"
    assert cfg.embeddings.provider == "ollama"
    assert cfg.llm.model == "claude-sonnet-4-6"
    assert cfg.gigaflow.enabled is False


def test_load_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")
