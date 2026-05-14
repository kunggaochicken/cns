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


def test_loads_capture_and_webhooks_sections(tmp_path: Path):
    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text(
        "capture:\n"
        "  backend_url: http://localhost:8001\n"
        "  timeout_seconds: 2.5\n"
        "webhooks:\n"
        "  linear_secret_env: LINEAR_WEBHOOK_SECRET\n"
        "  github_secret_env: GITHUB_WEBHOOK_SECRET\n"
    )
    cfg = load_config(cfg_path)
    assert cfg.capture.backend_url == "http://localhost:8001"
    assert cfg.capture.timeout_seconds == 2.5
    assert cfg.webhooks.linear_secret_env == "LINEAR_WEBHOOK_SECRET"
    assert cfg.webhooks.github_secret_env == "GITHUB_WEBHOOK_SECRET"


def test_capture_and_webhooks_default_when_omitted():
    from app.config import GigaBrainConfig

    cfg = GigaBrainConfig()
    assert cfg.capture.backend_url == "http://localhost:8001"
    assert cfg.capture.timeout_seconds == 5.0
    assert cfg.webhooks.linear_secret_env is None
    assert cfg.webhooks.github_secret_env is None


def test_loads_watchers_obsidian_section(tmp_path):
    from app.config import load_config

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text(
        "watchers:\n"
        "  obsidian:\n"
        "    enabled: true\n"
        "    debounce_seconds: 1.5\n"
        "    ignore_patterns:\n"
        "      - .git/*\n"
        "      - .obsidian/*\n"
    )
    cfg = load_config(cfg_path)
    assert cfg.watchers.obsidian.enabled is True
    assert cfg.watchers.obsidian.debounce_seconds == 1.5
    assert cfg.watchers.obsidian.ignore_patterns == [".git/*", ".obsidian/*"]


def test_watchers_obsidian_defaults():
    from app.config import GigaBrainConfig

    cfg = GigaBrainConfig()
    assert cfg.watchers.obsidian.enabled is False
    assert cfg.watchers.obsidian.debounce_seconds == 2.0
    assert ".git/*" in cfg.watchers.obsidian.ignore_patterns
