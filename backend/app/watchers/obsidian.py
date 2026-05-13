import asyncio
import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path

from watchfiles import Change, awatch

from app.capture.normalizer import normalize_and_persist
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus
from app.watchers.debounce import PerPathDebouncer

log = logging.getLogger(__name__)


def should_capture(
    *,
    vault: Path,
    path: Path,
    ignore_patterns: list[str],
) -> bool:
    """Return True if `path` is a markdown file inside `vault` that does not
    match any of `ignore_patterns` (fnmatch against the vault-relative path).
    """
    vault = vault.resolve()
    try:
        rel = path.resolve().relative_to(vault)
    except ValueError:
        return False
    if path.suffix.lower() != ".md":
        return False
    rel_str = str(rel)
    for pat in ignore_patterns:
        if fnmatch.fnmatch(rel_str, pat):
            return False
        # Also match any path component (e.g. ".git/*" against "Notes/.git/x.md").
        for part in rel.parts:
            if fnmatch.fnmatch(part, pat.rstrip("/*")):
                return False
    return True


@dataclass
class ObsidianWatcher:
    vault: Path
    nodes: NodeRepository
    vec: VectorStore
    bus: EventBus
    embedder: EmbeddingsProvider
    debounce_seconds: float
    ignore_patterns: list[str]

    async def run(self) -> None:
        """Long-running task. Cancel to stop."""
        if not self.vault.exists():
            log.warning(
                "Obsidian watcher: vault path %s does not exist; not starting",
                self.vault,
            )
            return

        debouncer = PerPathDebouncer(window_seconds=self.debounce_seconds)

        async def emit_loop():
            async for path_str in debouncer.stream():
                try:
                    await self._handle_path(Path(path_str))
                except Exception:
                    log.exception("Obsidian watcher: failed to capture %s", path_str)

        emit_task = asyncio.create_task(emit_loop())
        try:
            async for changes in awatch(str(self.vault)):
                for change_type, raw_path in changes:
                    if change_type == Change.deleted:
                        continue
                    debouncer.push(raw_path)
        finally:
            debouncer.close()
            await emit_task

    async def _handle_path(self, path: Path) -> None:
        if not should_capture(
            vault=self.vault,
            path=path,
            ignore_patterns=self.ignore_patterns,
        ):
            return
        try:
            content = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            return
        if not content.strip():
            return
        rel = path.resolve().relative_to(self.vault.resolve())
        await normalize_and_persist(
            content=content,
            source="obsidian",
            metadata={"vault_path": str(rel)},
            nodes=self.nodes,
            vec=self.vec,
            bus=self.bus,
            embedder=self.embedder,
        )
