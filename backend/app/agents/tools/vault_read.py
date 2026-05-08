from pathlib import Path

from app.agents.tools.base import Tool, ToolContext


class VaultReadTool(Tool):
    name = "vault_read"

    async def run(self, ctx: ToolContext, *, path: str) -> str:
        vault = Path(ctx.vault_path).resolve()
        target = (vault / path).resolve()
        if not target.is_relative_to(vault):
            raise ValueError(f"Path {path!r} resolves outside vault")
        if not target.exists():
            raise FileNotFoundError(f"Vault file not found: {path}")
        return target.read_text()
