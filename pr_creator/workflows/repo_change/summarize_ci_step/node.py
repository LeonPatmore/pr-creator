from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.repo_change.ci_types import CiFailure
from pr_creator.workflows.repo_change.summarize_ci_step.agent import (
    build_ci_failure_summarizer,
)

logger = logging.getLogger(__name__)


def _failure_prompt(f: CiFailure) -> tuple[str, str]:
    name = f.name or "check"
    pr_url = f.pr_url or ""
    head_sha = f.head_sha or ""
    details = f.details_url or ""
    logs = (f.logs or "").strip()
    prompt = "\n".join(
        [
            f"check_name: {name}",
            f"pr_url: {pr_url}",
            f"head_sha: {head_sha}",
            f"details_url: {details}",
            "",
            "logs:",
            logs or "No logs available.",
        ]
    ).strip()
    return name, prompt


@dataclass
class SummarizeCiFailures(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        failures = (ctx.state.ci_failures or {}).get(self.repo_url) or []
        items = [_failure_prompt(f) for f in failures]
        if not items:
            logger.info(
                "[ci-summary] no CI failure payload to summarize for %s", self.repo_url
            )
            from pr_creator.workflows.repo_change.cleanup_step.node import CleanupRepo

            return CleanupRepo(repo_url=self.repo_url)

        logger.info(
            "[ci-summary] summarizing %d CI failure(s) for %s",
            len(items),
            self.repo_url,
        )

        summaries: list[str] = []
        async with build_ci_failure_summarizer() as summarize_one:
            # Summaries are independent; run them concurrently but keep output ordering stable.
            tasks = [summarize_one(prompt) for _name, prompt in items]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for (name, _prompt), result in zip(items, results):
            if isinstance(result, Exception):
                fallback = f"CI failed in {name}. Check the CI logs for details."
                summaries.append(fallback)
                logger.warning(
                    "[ci-summary] summarizer errored for %s: %s", name, result
                )
                logger.info("[ci-summary] %s: %s", name, fallback)
                continue

            s = (result or "").strip()
            if not s:
                s = f"CI failed in {name}. Check the CI logs for details."
            summaries.append(s)
            logger.info("[ci-summary] %s: %s", name, s)

        ctx.state.ci_failure_summaries[self.repo_url] = summaries

        from pr_creator.workflows.repo_change.cleanup_step.node import CleanupRepo

        return CleanupRepo(repo_url=self.repo_url)
