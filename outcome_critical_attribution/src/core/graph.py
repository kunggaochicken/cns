"""Attribution graphs and support graphs.

An AttributionGraph is a directed graph whose edges claim "atom A contributed
to atom B". A SupportGraph is the pruned subgraph that is sufficient to support
a success certificate.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from core.atoms import Atom


@dataclass
class AttributionEdge:
    """A directed, weighted "contributed to" edge between two atoms."""

    source_atom_id: str
    target_atom_id: str
    weight: float
    method: str
    evidence: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttributionGraph:
    """Directed graph of attribution edges over a pool of atoms."""

    atoms: dict[str, Atom]
    edges: list[AttributionEdge] = field(default_factory=list)

    def incoming_edges(self, atom_id: str) -> list[AttributionEdge]:
        return [e for e in self.edges if e.target_atom_id == atom_id]

    def outgoing_edges(self, atom_id: str) -> list[AttributionEdge]:
        return [e for e in self.edges if e.source_atom_id == atom_id]

    def upstream_atoms(self, atom_ids: list[str], min_weight: float = 0.0) -> set[str]:
        """Transitive closure of sources reachable backward from `atom_ids`.

        Follows incoming edges with weight >= `min_weight`. The seed ids
        themselves are not included unless something points into them and is
        itself reached.
        """
        # Index incoming edges once for an O(V+E) traversal.
        incoming: dict[str, list[AttributionEdge]] = {}
        for e in self.edges:
            if e.weight >= min_weight:
                incoming.setdefault(e.target_atom_id, []).append(e)

        seen: set[str] = set()
        queue: deque[str] = deque(atom_ids)
        while queue:
            current = queue.popleft()
            for edge in incoming.get(current, []):
                src = edge.source_atom_id
                if src not in seen:
                    seen.add(src)
                    queue.append(src)
        return seen


@dataclass
class SupportGraph:
    """The minimal upstream subgraph that supports a success certificate."""

    atom_ids: list[str]
    edges: list[AttributionEdge] = field(default_factory=list)
    certificate_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __contains__(self, atom_id: str) -> bool:
        return atom_id in set(self.atom_ids)
