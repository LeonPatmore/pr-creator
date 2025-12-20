from __future__ import annotations

from .types import BaseNode, End, GraphRunContext


class NextRepo(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End | None:
        if not ctx.state.repos:
            return End()
        repo_url = ctx.state.repos.pop(0)
        from .clone import CloneRepo

        return CloneRepo(repo_url=repo_url)

