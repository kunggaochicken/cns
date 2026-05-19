"""Applying a trained context policy to compress a trajectory."""

from __future__ import annotations

from dataclasses import dataclass

from core.atoms import Atom

from policy.model import ContextPolicy


@dataclass
class CompressionResult:
    """The output of compressing a trajectory's atoms."""

    kept_atoms: list[Atom]
    dropped_atoms: list[Atom]
    kept_tokens: int
    total_tokens: int

    @property
    def compression_ratio(self) -> float:
        return len(self.kept_atoms) / max(1, len(self.kept_atoms) + len(self.dropped_atoms))

    @property
    def token_savings(self) -> float:
        return 1.0 - self.kept_tokens / max(1, self.total_tokens)


def compress_trajectory(
    policy: ContextPolicy,
    atoms: list[Atom],
    budget_tokens: int | None = None,
    threshold: float | None = None,
) -> CompressionResult:
    """Run a policy over trajectory atoms and report what was kept/dropped."""
    kept = policy.select_atoms(atoms, budget_tokens=budget_tokens, threshold=threshold)
    kept_ids = {id(a) for a in kept}
    dropped = [a for a in atoms if id(a) not in kept_ids]
    return CompressionResult(
        kept_atoms=kept,
        dropped_atoms=dropped,
        kept_tokens=sum(a.token_count for a in kept),
        total_tokens=sum(a.token_count for a in atoms),
    )
