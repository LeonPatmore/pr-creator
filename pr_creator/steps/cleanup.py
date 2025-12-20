from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext
from .next_repo import NextRepo

logger = logging.getLogger(__name__)


@dataclass
class CleanupRepo(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned.get(self.repo_url)
        if path:
            try:
                shutil.rmtree(path, ignore_errors=True)
                logger.info("Cleaned up cloned repo at %s", path)
            except Exception as exc:
                logger.warning("Failed to clean up %s: %s", path, exc)
        return NextRepo()

