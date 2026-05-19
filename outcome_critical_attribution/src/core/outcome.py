"""The final outcome an agent produced for a task."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Outcome:
    """The end state / final response produced by an agent.

    `content` is the primary textual representation (final answer, final
    response, serialized final state). `artifacts` holds opaque references to
    anything heavier (file paths, URLs, blob ids) the oracle may consult.
    """

    id: str
    task_id: str
    domain: str
    content: str
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
