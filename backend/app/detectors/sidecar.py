from datetime import UTC, datetime
from pathlib import Path


def write_conflict_sidecar(
    *,
    vault_path: str | Path,
    conflict_id: str,
    summary: str,
    new_thought_id: str,
    new_thought_content: str,
    candidate_thought_id: str,
    candidate_thought_content: str,
    confidence: float,
) -> Path:
    """Single-console principle: every auto-created Conflict gets a markdown
    sidecar in Brain/Reviews/conflicts/<conflict-id>.md so the leader never
    has to leave the vault to see what was flagged.
    """
    out_dir = Path(vault_path) / "Brain" / "Reviews" / "conflicts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{conflict_id}.md"
    now = datetime.now(UTC).isoformat()
    out_path.write_text(
        f"""---
conflict_id: {conflict_id}
detected_at: {now}
confidence: {confidence:.2f}
status: open
---

# Conflict: {summary}

## New thought (`{new_thought_id}`)

{new_thought_content}

## Conflicts with (`{candidate_thought_id}`)

{candidate_thought_content}
"""
    )
    return out_path
