import asyncio

from app.agents.tools.base import Tool, ToolContext


class StageCommitsTool(Tool):
    name = "stage_commits"

    async def run(self, ctx: ToolContext, *, files: list[str], message: str) -> str:
        if not ctx.repo_path:
            raise ValueError("stage_commits requires ToolContext.repo_path; got None")
        if not files:
            raise ValueError("stage_commits requires at least one file")

        # Stage
        add_proc = await asyncio.create_subprocess_exec(
            "git",
            "add",
            *files,
            cwd=ctx.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await add_proc.communicate()
        if add_proc.returncode != 0:
            raise RuntimeError(f"git add failed (exit {add_proc.returncode})")

        # Commit (no push, ever)
        commit_proc = await asyncio.create_subprocess_exec(
            "git",
            "commit",
            "-m",
            message,
            cwd=ctx.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await commit_proc.communicate()
        return (stdout or b"").decode() + (stderr or b"").decode()
