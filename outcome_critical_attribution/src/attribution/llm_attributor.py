"""LLM-backed attribution.

`PromptLLMAttributor` builds a prompt asking a model to trace which trajectory
atoms contributed to each outcome atom, then parses the reply into edges.

The LLM is injected as a plain `Callable[[str], str]` -- no provider is
hardcoded. Wire in OpenAI, Anthropic, a local model, or a stub as you like::

    attributor = PromptLLMAttributor(generate=my_generate_fn)
"""

from __future__ import annotations

import re
from collections.abc import Callable

from core.atoms import Atom, OutcomeAtom
from core.graph import AttributionEdge, AttributionGraph

from attribution.graph_builder import build_graph

GenerateFn = Callable[[str], str]

_PROMPT_TEMPLATE = """You are tracing information flow in an agent trajectory.

TRAJECTORY ATOMS (things the agent saw, did, or produced):
{trajectory_block}

REQUIRED OUTCOME ATOMS (parts of the final outcome that were proven necessary
for the task to succeed):
{outcome_block}

For each required outcome atom, identify which trajectory atoms contributed to
it -- i.e. supplied information, decisions, or actions that the outcome atom
depended on.

Return one edge per line, and nothing else, in exactly this format:

  <source_trajectory_atom_id> -> <target_outcome_atom_id> | <weight> | <why>

where <weight> is a number from 0 to 1. Omit edges weaker than 0.1.
"""


def _format_atoms(atoms: list[Atom]) -> str:
    lines = []
    for a in atoms:
        snippet = a.content.replace("\n", " ").strip()
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        lines.append(f"[{a.id}] ({a.atom_type}) {snippet}")
    return "\n".join(lines)


def build_attribution_prompt(trajectory_atoms: list[Atom], outcome_atoms: list[OutcomeAtom]) -> str:
    return _PROMPT_TEMPLATE.format(
        trajectory_block=_format_atoms(trajectory_atoms),
        outcome_block=_format_atoms(list(outcome_atoms)),
    )


_EDGE_LINE = re.compile(
    r"^\s*(?P<src>[\w.\-]+)\s*->\s*(?P<dst>[\w.\-]+)\s*"
    r"\|\s*(?P<weight>[0-9.]+)\s*(?:\|\s*(?P<why>.*))?$"
)


def parse_attribution_response(text: str, valid_ids: set[str]) -> list[AttributionEdge]:
    """Parse the model reply into edges, dropping malformed/unknown-id lines."""
    edges: list[AttributionEdge] = []
    for raw in text.splitlines():
        m = _EDGE_LINE.match(raw)
        if not m:
            continue
        src, dst = m.group("src"), m.group("dst")
        if src not in valid_ids or dst not in valid_ids:
            continue
        try:
            weight = max(0.0, min(1.0, float(m.group("weight"))))
        except ValueError:
            continue
        edges.append(
            AttributionEdge(
                source_atom_id=src,
                target_atom_id=dst,
                weight=weight,
                method="llm_prompt",
                evidence=(m.group("why") or "").strip() or None,
            )
        )
    return edges


class PromptLLMAttributor:
    """Prompt-based attributor (implements the AttributionModel protocol)."""

    def __init__(self, generate: GenerateFn | None = None) -> None:
        self.generate = generate

    def attribute(
        self,
        trajectory_atoms: list[Atom],
        outcome_atoms: list[OutcomeAtom],
    ) -> AttributionGraph:
        if self.generate is None:
            raise RuntimeError(
                "PromptLLMAttributor needs a `generate` callable. Pass one in, "
                "or use HeuristicAttributor for a no-LLM run."
            )
        prompt = build_attribution_prompt(trajectory_atoms, outcome_atoms)
        reply = self.generate(prompt)
        valid_ids = {a.id for a in trajectory_atoms} | {a.id for a in outcome_atoms}
        edges = parse_attribution_response(reply, valid_ids)
        return build_graph(trajectory_atoms, outcome_atoms, edges)
