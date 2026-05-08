import asyncio

from app.agents.tools.base import Tool, ToolContext


class RunTestsTool(Tool):
    name = "run_tests"

    def __init__(self, command: str = "pytest -q"):
        self.command = command

    async def run(self, ctx: ToolContext) -> str:
        if not ctx.repo_path:
            raise ValueError(
                "run_tests requires ToolContext.repo_path; got no repo_path"
            )
        proc = await asyncio.create_subprocess_shell(
            self.command,
            cwd=ctx.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        body = (stdout or b"").decode() + (stderr or b"").decode()
        suffix = "" if proc.returncode == 0 else f"\n[exit code {proc.returncode}]"
        return body + suffix
