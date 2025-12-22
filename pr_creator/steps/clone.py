from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from dulwich import porcelain
from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.git_urls import token_auth_github_url

logger = logging.getLogger(__name__)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def clone_repo(repo_url: str, working_dir: Path) -> Path:
    ensure_dir(working_dir)
    name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    target = working_dir / name
    if target.exists():
        target = working_dir / f"{name}-{uuid.uuid4().hex[:8]}"
    logger.info("Cloning %s -> %s", repo_url, target)

    clone_url = repo_url
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        token_url = token_auth_github_url(repo_url, token)
        if token_url:
            clone_url = token_url

    porcelain.clone(clone_url, target, checkout=True)
    return target


@dataclass
class CloneRepo(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = clone_repo(self.repo_url, ctx.state.working_dir)
        ctx.state.cloned[self.repo_url] = path
        from .evaluate import EvaluateRelevance

        return EvaluateRelevance(repo_url=self.repo_url)
