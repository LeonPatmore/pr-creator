from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.repo_workspace import prepare_workspace
from pr_creator.workflows.orchestrator.evaluate_relevance_step.evaluate_agents.factory import (
    get_evaluate_agent,
)

logger = logging.getLogger(__name__)

_agent = get_evaluate_agent()


@dataclass
class EvaluateRelevanceOrchestrator(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        # If relevance_prompt is empty, treat all repos as relevant.
        if not ctx.state.relevance_prompt:
            from pr_creator.workflows.orchestrator.orchestrate_change_step.node import (
                OrchestrateChange,
            )

            return OrchestrateChange(repo_url=self.repo_url)

        # Prepare a read-only planning clone for evaluation.
        planning_dir = Path(ctx.state.working_dir) / "_orchestrator"
        repo_clone = prepare_workspace(
            repo=self.repo_url,
            working_dir=planning_dir,
            branch_name=None,
            stable=True,
            readonly=True,
        )
        ctx.state.planning_clones[self.repo_url] = repo_clone.path

        is_relevant = _agent.evaluate(repo_clone.path, ctx.state.relevance_prompt)
        logger.info("[orchestrator] relevance %s -> %s", self.repo_url, is_relevant)

        if not is_relevant:
            ctx.state.irrelevant.append(self.repo_url)
            from pr_creator.workflows.orchestrator.next_repo_step.node import (
                NextRepoOrchestrator,
            )

            return NextRepoOrchestrator()

        from pr_creator.workflows.orchestrator.orchestrate_change_step.node import (
            OrchestrateChange,
        )

        return OrchestrateChange(repo_url=self.repo_url)
