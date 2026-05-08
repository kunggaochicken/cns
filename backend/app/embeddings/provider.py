from abc import ABC, abstractmethod


class EmbeddingsProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @property
    @abstractmethod
    def dim(self) -> int: ...
