from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.github_actions import load_ci_wait_config, wait_for_ci

logger = logging.getLogger(__name__)


def _max_ci_attempts() -> int:
    try:
        return int(os.environ.get("CI_FIX_MAX_ATTEMPTS", "2").strip())
    except Exception:
        return 2


def _last_pr_url_for_repo(ctx: GraphRunContext, repo_url: str) -> str | None:
    for pr in reversed(ctx.state.created_prs):
        if pr.get("repo_url") == repo_url:
            return pr.get("pr_url")
    return None


def _last_pr_record_for_repo(
    ctx: GraphRunContext, repo_url: str
) -> dict[str, str] | None:
    for pr in reversed(ctx.state.created_prs):
        if pr.get("repo_url") == repo_url:
            return pr
    return None


def _summarize_ci_message(message: str) -> str:
    """
    CI failure messages can include large logs. This produces a small summary
    suitable for logging.
    """
    lines = [ln.strip() for ln in (message or "").splitlines() if ln.strip()]
    head_sha = next((ln for ln in lines if ln.startswith("- head_sha:")), None)
    summary = next((ln for ln in lines if ln.startswith("- summary:")), None)
    status = next((ln for ln in lines if ln.startswith("- status:")), None)
    parts = [p for p in (head_sha, summary, status) if p]
    return " ".join(parts) if parts else (lines[0] if lines else "CI failure")


@dataclass
class WaitForActions(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        pr_record = _last_pr_record_for_repo(ctx, self.repo_url)
        pr_url = (pr_record or {}).get("pr_url")
        if not pr_url:
            logger.info("[ci] no PR url for %s; skipping wait", self.repo_url)
            from .cleanup import CleanupRepo

            return CleanupRepo(repo_url=self.repo_url)

        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            logger.warning("[ci] GITHUB_TOKEN not set; skipping wait for %s", pr_url)
            from .cleanup import CleanupRepo

            return CleanupRepo(repo_url=self.repo_url)

        cfg = load_ci_wait_config()
        logger.info(
            "[ci] waiting for checks: pr=%s timeout=%ss poll=%ss acceptable_conclusions=%s",
            pr_url,
            cfg.timeout_seconds,
            cfg.poll_seconds,
            ",".join(cfg.acceptable_conclusions),
        )

        expected_head_sha = (pr_record or {}).get("pushed_sha")
        ok, message = wait_for_ci(
            pr_url, token=token, cfg=cfg, expected_head_sha=expected_head_sha
        )
        if ok:
            logger.info("[ci] %s", message)
            from .cleanup import CleanupRepo

            return CleanupRepo(repo_url=self.repo_url)

        attempts = ctx.state.ci_attempts.get(self.repo_url, 0)
        max_attempts = _max_ci_attempts()
        logger.warning(
            "[ci] failure (attempt %s/%s) %s (details stored for agent; bytes=%s)",
            attempts,
            max_attempts,
            _summarize_ci_message(message),
            len(message.encode("utf-8", errors="ignore")),
        )

        if attempts < max_attempts:
            ctx.state.ci_attempts[self.repo_url] = attempts + 1
            ctx.state.ci_pending[self.repo_url] = message
            from .apply import ApplyChanges

            return ApplyChanges(repo_url=self.repo_url)

        logger.warning(
            "[ci] still failing after %s attempt(s) (max=%s); proceeding to cleanup",
            attempts,
            max_attempts,
        )
        from .cleanup import CleanupRepo

        return CleanupRepo(repo_url=self.repo_url)
