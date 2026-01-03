from __future__ import annotations

import logging
from dataclasses import dataclass

from pr_creator.change_agents import get_change_agent

from pydantic_graph import BaseNode, End, GraphRunContext

logger = logging.getLogger(__name__)

_agent = get_change_agent()


@dataclass
class ApplyChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        logger.info("Applying change agent on %s at %s", self.repo_url, path)

        ci_pending = ctx.state.ci_pending.pop(self.repo_url, "").strip()
        pending = ctx.state.review_pending.pop(self.repo_url, "").strip()
        if ci_pending or pending:
            sections: list[str] = []
            if ci_pending:
                sections.append(
                    "## CRITICAL: Fix failing CI / GitHub Actions\n"
                    "The PR is failing CI. Use the logs below to fix the issue.\n"
                    "If there is a conflict, prioritize this section.\n\n"
                    f"{ci_pending}\n"
                )
            if pending:
                sections.append(
                    "## CRITICAL: Address review feedback\n"
                    "Apply the following review feedback before doing anything else.\n"
                    "If there is a conflict, prioritize this section.\n\n"
                    f"{pending}\n"
                )
            prompt = (
                "\n\n".join(sections).rstrip() + "\n\n"
                "## Original request (retain intent)\n"
                f"{ctx.state.prompt.strip()}\n"
            )
        else:
            prompt = ctx.state.prompt
        _agent.run(
            path,
            prompt,
            context_roots=ctx.state.context_roots,
            secrets=ctx.state.change_agent_secrets,
        )
        ctx.state.processed.append(self.repo_url)
        from .review import ReviewChanges

        return ReviewChanges(repo_url=self.repo_url)
