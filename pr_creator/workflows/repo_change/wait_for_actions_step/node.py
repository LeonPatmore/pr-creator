from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from functools import partial

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.repo_change.ci_types import CiFailure
from pr_creator.workflows.repo_change.wait_for_actions_step.github_actions import (
    load_ci_wait_config,
    wait_for_ci,
)

logger = logging.getLogger(__name__)


def _max_ci_attempts() -> int:
    try:
        return int(os.environ.get("CI_FIX_MAX_ATTEMPTS", "2").strip())
    except Exception:
        return 2


def _summarize_ci_failures(failures: list[CiFailure]) -> str:
    """
    CI failures can include large logs. This produces a small summary suitable for logging.
    """
    if not failures:
        return "CI failure"
    names = ", ".join(f.name for f in failures[:4] if getattr(f, "name", None))
    suffix = "…" if len(failures) > 4 else ""
    head_sha = failures[0].head_sha[:12] if failures[0].head_sha else ""
    return f"head_sha={head_sha} failures={len(failures)} [{names}{suffix}]".strip()


@dataclass
class WaitForActions(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        pr_url = ctx.state.created_pr
        if not pr_url:
            logger.info("[ci] no PR url for %s; skipping wait", self.repo_url)
            from pr_creator.workflows.repo_change.cleanup_step.node import CleanupRepo

            return CleanupRepo(repo_url=self.repo_url)

        token = ctx.state.github_token
        if not token:
            logger.warning("[ci] GitHub token not set; skipping wait for %s", pr_url)
            from pr_creator.workflows.repo_change.cleanup_step.node import CleanupRepo

            return CleanupRepo(repo_url=self.repo_url)

        cfg = load_ci_wait_config()
        logger.info(
            "[ci] waiting for checks: pr=%s timeout=%ss poll=%ss acceptable_conclusions=%s",
            pr_url,
            cfg.timeout_seconds,
            cfg.poll_seconds,
            ",".join(cfg.acceptable_conclusions),
        )

        attempts = ctx.state.ci_attempts.get(self.repo_url, 0)
        max_attempts = _max_ci_attempts()
        # On the final attempt (no retries left), do NOT fail fast on the first failed check.
        # Instead, wait for all checks to reach terminal state so we can summarize all failures.
        fail_fast_on_failure = attempts < max_attempts

        expected_head_sha = ctx.state.created_pr_pushed_sha
        # CI polling does network + sleeps (blocking); offload so repo workflows can run in parallel.
        failures = await asyncio.to_thread(
            partial(
                wait_for_ci,
                pr_url,
                token=token,
                cfg=cfg,
                expected_head_sha=expected_head_sha,
                fail_fast_on_failure=fail_fast_on_failure,
            )
        )
        if not failures:
            logger.info("[ci] all checks passed for %s", pr_url)
            ctx.state.ci_passed = True
            from pr_creator.workflows.repo_change.cleanup_step.node import CleanupRepo

            return CleanupRepo(repo_url=self.repo_url)

        logger.warning(
            "[ci] failure (attempt %s/%s) %s",
            attempts,
            max_attempts,
            _summarize_ci_failures(failures),
        )

        if attempts < max_attempts:
            ctx.state.ci_attempts[self.repo_url] = attempts + 1
            ctx.state.ci_failures[self.repo_url] = failures
            from pr_creator.workflows.repo_change.apply_step.node import ApplyChanges

            return ApplyChanges(repo_url=self.repo_url)

        logger.warning(
            "[ci] still failing after %s attempt(s) (max=%s); proceeding to cleanup",
            attempts,
            max_attempts,
        )
        ctx.state.ci_passed = False
        # Capture the final CI failure list so we can summarize it (one summary per failed check).
        ctx.state.ci_failures[self.repo_url] = failures
        from pr_creator.workflows.repo_change.summarize_ci_step.node import (
            SummarizeCiFailures,
        )

        return SummarizeCiFailures(repo_url=self.repo_url)
