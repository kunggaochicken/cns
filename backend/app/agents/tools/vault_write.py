from pathlib import Path

from app.agents.tools.base import Tool, ToolContext


class VaultWriteTool(Tool):
    name = "vault_write"

    async def run(self, ctx: ToolContext, *, path: str, content: str) -> str:
        vault = Path(ctx.vault_path).resolve()
        target = (vault / path).resolve()
        if not str(target).startswith(str(vault)):
            raise ValueError(f"Path {path!r} resolves outside vault")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"wrote {len(content)} bytes to {path}"
