from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class DetectorOutcome(BaseModel):
    """Returned by every detector for telemetry/logging. Not persisted."""

    detector: str
    thought_id: str
    candidates_examined: int = 0
    edges_written: int = 0
    nodes_written: int = 0


@runtime_checkable
class Detector(Protocol):
    name: str

    async def run(
        self,
        *,
        thought_id: str,
        content: str,
        embedding: list[float],
    ) -> DetectorOutcome: ...
