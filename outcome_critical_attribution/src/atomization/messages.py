"""Text-splitting helpers shared by atomizers.

These are deliberately simple and dependency-free: paragraph, bullet, and
sentence splitting. Domain-specific atomizers can compose or replace them.
"""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines."""
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def split_bullets(text: str) -> list[str]:
    """Split a block into bullet/numbered list items, falling back to lines."""
    items: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        items.append(_BULLET.sub("", line).strip())
    return [i for i in items if i]


def split_sentences(text: str) -> list[str]:
    """Naive sentence splitter."""
    parts = _SENTENCE_END.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def split_units(text: str) -> list[str]:
    """Best-effort generic split into claim-sized units.

    Prefers bullets when the block looks like a list, then paragraphs, then
    sentences within multi-sentence paragraphs.
    """
    text = (text or "").strip()
    if not text:
        return []

    bullet_lines = [ln for ln in text.splitlines() if _BULLET.match(ln)]
    if len(bullet_lines) >= 2:
        return split_bullets(text)

    units: list[str] = []
    for para in split_paragraphs(text):
        sentences = split_sentences(para)
        units.extend(sentences if len(sentences) > 1 else [para])
    return units or [text]
