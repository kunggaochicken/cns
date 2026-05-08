from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class DBConfig(BaseModel):
    kuzu_path: str = "./data/gigabrain.kuzu"
    vector_path: str = "./data/gigabrain-vec.sqlite"


class EmbeddingsConfig(BaseModel):
    provider: Literal["ollama", "openai"] = "ollama"
    model: str = "nomic-embed-text"
    base_url: str = "http://localhost:11434"
    api_key_env: str | None = None


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "file://./data/traces"


class GigaFlowConfig(BaseModel):
    enabled: bool = False
    manifest_url: str | None = None
    poll_interval_minutes: int = 60


class GigaBrainConfig(BaseModel):
    db: DBConfig = DBConfig()
    embeddings: EmbeddingsConfig = EmbeddingsConfig()
    llm: LLMConfig = LLMConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    gigaflow: GigaFlowConfig = GigaFlowConfig()


def load_config(path: Path | str) -> GigaBrainConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return GigaBrainConfig.model_validate(data)
