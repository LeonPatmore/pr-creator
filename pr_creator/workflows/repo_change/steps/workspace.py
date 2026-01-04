from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.repo_workspace import CloneResult, prepare_workspace

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceRepo(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        branch_name = ctx.state.branches.get(self.repo_url)
        result = prepare_workspace(
            repo=self.repo_url,
            working_dir=ctx.state.working_dir,
            change_id=ctx.state.change_id,
            branch_name=branch_name,
        )
        assert isinstance(result, CloneResult)
        ctx.state.cloned[self.repo_url] = result.path
        ctx.state.branches[self.repo_url] = result.branch

        if result.branch_exists_remotely:
            logger.info(
                "Branch exists remotely for %s, skipping relevance check (will re-apply changes)",
                self.repo_url,
            )
            ctx.state.relevant.append(self.repo_url)
            from .apply import ApplyChanges

            return ApplyChanges(repo_url=self.repo_url)

        # Relevance evaluation is orchestrator-owned. Repo-change runs assume the repo
        # is already selected.
        from .apply import ApplyChanges

        return ApplyChanges(repo_url=self.repo_url)
