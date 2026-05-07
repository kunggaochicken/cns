import ollama

from app.config import EmbeddingsConfig
from app.embeddings.provider import EmbeddingsProvider


class OllamaEmbedder(EmbeddingsProvider):
    # nomic-embed-text default; configurable
    _MODEL_DIMS = {"nomic-embed-text": 768, "mxbai-embed-large": 1024}

    def __init__(self, cfg: EmbeddingsConfig):
        self.cfg = cfg
        self._client = ollama.AsyncClient(host=cfg.base_url)

    @property
    def dim(self) -> int:
        return self._MODEL_DIMS.get(self.cfg.model, 768)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings(model=self.cfg.model, prompt=text)
        return list(response["embedding"])
