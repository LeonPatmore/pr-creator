import asyncio
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .change_agent import ChangeAgent
from .pr_interface import PRInterface
from .state import WorkflowState

try:
    from pydantic_ai.graph import BaseNode, End, Graph, GraphRunContext
except Exception:
    @dataclass
    class GraphRunContext:
        state: WorkflowState

    class BaseNode:
        async def run(self, ctx: GraphRunContext) -> Optional["BaseNode"]:
            raise NotImplementedError

    class End(BaseNode):
        async def run(self, ctx: GraphRunContext) -> Optional["BaseNode"]:
            return None

    class Graph:
        def __init__(self, nodes=None, state_type=None) -> None:
            self.nodes = nodes or []
            self.state_type = state_type

        async def run(self, start_node: BaseNode, state: WorkflowState) -> WorkflowState:
            ctx = GraphRunContext(state=state)
            node: Optional[BaseNode] = start_node
            while node is not None:
                node = await node.run(ctx)
            return state


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def clone_repo(repo_url: str, working_dir: Path) -> Path:
    ensure_dir(working_dir)
    name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    target = working_dir / name
    if target.exists():
        target = working_dir / f"{name}-{uuid.uuid4().hex[:8]}"
    subprocess.run(["git", "clone", repo_url, str(target)], check=True)
    return target


def evaluate_relevance(relevance_prompt: str, repo_path: Path) -> bool:
    return True


class NextRepo(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End | None:
        if not ctx.state.repos:
            return End()
        repo_url = ctx.state.repos.pop(0)
        return CloneRepo(repo_url=repo_url)


@dataclass
class CloneRepo(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End | None:
        path = clone_repo(self.repo_url, ctx.state.working_dir)
        ctx.state.cloned[self.repo_url] = path
        return EvaluateRelevance(repo_url=self.repo_url)


@dataclass
class EvaluateRelevance(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End | None:
        path = ctx.state.cloned[self.repo_url]
        if evaluate_relevance(ctx.state.relevance_prompt, path):
            ctx.state.relevant.append(self.repo_url)
            return ApplyChanges(repo_url=self.repo_url)
        return NextRepo()


@dataclass
class ApplyChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End | None:
        path = ctx.state.cloned[self.repo_url]
        ChangeAgent.run(path, ctx.state.prompt)
        ctx.state.processed.append(self.repo_url)
        return CreateOrUpdatePR(repo_url=self.repo_url)


@dataclass
class CreateOrUpdatePR(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End | None:
        path = ctx.state.cloned[self.repo_url]
        PRInterface.create_or_update_pr(path)
        return NextRepo()


def build_graph() -> Graph:
    try:
        return Graph(nodes=[NextRepo, CloneRepo, EvaluateRelevance, ApplyChanges, CreateOrUpdatePR], state_type=WorkflowState)
    except Exception:
        return Graph(nodes=[NextRepo, CloneRepo, EvaluateRelevance, ApplyChanges, CreateOrUpdatePR])


async def run_workflow(state: WorkflowState) -> WorkflowState:
    graph = build_graph()
    runner = getattr(graph, "run", None)
    if asyncio.iscoroutinefunction(runner):
        return await runner(start_node=NextRepo(), state=state)
    if runner is not None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: runner(start_node=NextRepo(), state=state))
    ctx = GraphRunContext(state=state)
    node: Optional[BaseNode] = NextRepo()
    while node is not None:
        node = await node.run(ctx)
    return state

