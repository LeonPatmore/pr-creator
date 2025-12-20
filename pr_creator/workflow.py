import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from .logging_config import ensure_logging_configured
from .state import WorkflowState
from .steps import ApplyChanges, CleanupRepo, CloneRepo, EvaluateRelevance, NextRepo
from .steps.types import BaseNode, End, GraphRunContext

logger = logging.getLogger(__name__)


@dataclass
class Graph:
    nodes: list | None = None
    state_type: type | None = None

    async def run(self, start_node: BaseNode, state: WorkflowState) -> WorkflowState:
        ctx = GraphRunContext(state=state)
        node: Optional[BaseNode] = start_node
        while node is not None:
            node = await node.run(ctx)
        return state


def build_graph() -> Graph:
    return Graph(nodes=[NextRepo, CloneRepo, EvaluateRelevance, ApplyChanges, CleanupRepo], state_type=WorkflowState)


async def run_workflow(state: WorkflowState) -> WorkflowState:
    ensure_logging_configured()
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

