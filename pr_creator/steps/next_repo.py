from __future__ import annotations

from pydantic_graph import BaseNode, End, GraphRunContext


class NextRepo(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        if not ctx.state.repos:
            return End(None)
        repo_url = ctx.state.repos.pop(0)
        from .clone import CloneRepo

        return CloneRepo(repo_url=repo_url)
