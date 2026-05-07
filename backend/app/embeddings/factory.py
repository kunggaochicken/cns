from app.config import EmbeddingsConfig
from app.embeddings.ollama import OllamaEmbedder
from app.embeddings.provider import EmbeddingsProvider


def build_provider(cfg: EmbeddingsConfig) -> EmbeddingsProvider:
    if cfg.provider == "ollama":
        return OllamaEmbedder(cfg)
    raise ValueError(f"Unsupported embeddings provider: {cfg.provider}")
