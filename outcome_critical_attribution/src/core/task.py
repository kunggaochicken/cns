"""A task is the unit of work an agent attempts, independent of any domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    """A domain-agnostic description of what an agent was asked to do.

    `domain` is a free-form string ("coding", "browser", "research", ...).
    No part of the core framework branches on its value.
    """

    id: str
    domain: str
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)
