from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.repo_workspace import prepare_workspace
from pr_creator.workflows.orchestrator.evaluate_relevance_step.relevance_cache import (
    DiskRelevanceCache,
    compute_prompt_hash,
    try_get_repo_head_sha,
)
from pr_creator.workflows.orchestrator.evaluate_relevance_step.evaluate_agents.factory import (
    get_evaluate_agent,
)

logger = logging.getLogger(__name__)

_agent = get_evaluate_agent()
_cache = DiskRelevanceCache()


def _evaluate_relevance_with_cache(
    *, repo_url: str, repo_path: Path, prompt: str
) -> bool:
    sha = try_get_repo_head_sha(repo_path)
    prompt_hash = compute_prompt_hash(prompt)

    if not sha:
        # If we cannot resolve a revision SHA, fall back to evaluating without caching.
        return _agent.evaluate(repo_path, prompt)

    cached = _cache.get(repo_identifier=repo_url, sha=sha, prompt_hash=prompt_hash)
    if cached is not None:
        logger.info(
            "[orchestrator] relevance cache hit repo=%s sha=%s prompt=%s -> %s",
            repo_url,
            sha[:8],
            prompt_hash[:8],
            cached,
        )
        return cached

    decision = _agent.evaluate(repo_path, prompt)
    _cache.set(
        repo_identifier=repo_url, sha=sha, prompt_hash=prompt_hash, value=decision
    )
    logger.info(
        "[orchestrator] relevance cache store repo=%s sha=%s prompt=%s -> %s",
        repo_url,
        sha[:8],
        prompt_hash[:8],
        decision,
    )
    return decision


@dataclass
class EvaluateRelevanceOrchestrator(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        # If relevance_prompt is empty, treat all repos as relevant.
        if not ctx.state.relevance_prompt:
            logger.info(
                "[orchestrator] relevance skipped for %s (no relevance_prompt provided)",
                self.repo_url,
            )
            from pr_creator.workflows.orchestrator.orchestrate_change_step.node import (
                OrchestrateChange,
            )

            return OrchestrateChange(repo_url=self.repo_url)

        # Prepare a read-only planning clone for evaluation.
        assert ctx.state.working_dir is not None
        planning_dir = Path(ctx.state.working_dir) / "_orchestrator"
        repo_clone = prepare_workspace(
            repo=self.repo_url,
            working_dir=planning_dir,
            github_token=ctx.state.github_token,
            branch_name=None,
            stable=True,
            readonly=True,
        )
        ctx.state.planning_clones[self.repo_url] = repo_clone.path

        is_relevant = _evaluate_relevance_with_cache(
            repo_url=self.repo_url,
            repo_path=repo_clone.path,
            prompt=ctx.state.relevance_prompt,
        )
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
