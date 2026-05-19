"""Artifact-splitting helpers.

Artifacts (files, documents, generated outputs) are split into sections so an
atomizer can treat each section as its own atom.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^(#{1,6}\s+.*|[A-Z][^\n]{0,60}:)\s*$")


def split_artifact_sections(text: str) -> list[str]:
    """Split an artifact into sections at markdown-style or `Label:` headings.

    Falls back to blank-line-separated blocks when no headings are present.
    """
    text = (text or "").strip()
    if not text:
        return []

    lines = text.splitlines()
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _HEADING.match(line) and current:
            sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)

    blocks = ["\n".join(s).strip() for s in sections]
    blocks = [b for b in blocks if b]
    if len(blocks) > 1:
        return blocks

    # No headings -> fall back to blank-line blocks.
    fallback = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return fallback or [text]
