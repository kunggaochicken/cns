import subprocess

from app.agents.tools.base import Tool, ToolContext


class StageCommitsTool(Tool):
    name = "stage_commits"

    async def run(self, ctx: ToolContext, *, files: list[str], message: str) -> str:
        if not ctx.repo_path:
            raise ValueError("stage_commits requires ToolContext.repo_path; got None")
        if not files:
            raise ValueError("stage_commits requires at least one file")
        subprocess.run(["git", "add", *files], cwd=ctx.repo_path, check=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=ctx.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout + result.stderr
