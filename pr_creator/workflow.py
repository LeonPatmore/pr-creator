import logging
from pydantic_graph import Graph
from .logging_config import ensure_logging_configured
from .state import WorkflowState
from .steps import (
    ApplyChanges,
    CleanupRepo,
    CloneRepo,
    DiscoverRepos,
    EvaluateRelevance,
    NextRepo,
    SubmitChanges,
)

logger = logging.getLogger(__name__)


def build_graph() -> Graph:
    return Graph(
        nodes=[
            DiscoverRepos,
            NextRepo,
            CloneRepo,
            EvaluateRelevance,
            ApplyChanges,
            SubmitChanges,
            CleanupRepo,
        ],
        state_type=WorkflowState,
    )


async def run_workflow(state: WorkflowState) -> WorkflowState:
    ensure_logging_configured()
    graph = build_graph()
    result = await graph.run(start_node=DiscoverRepos(), state=state)
    return result.state if hasattr(result, "state") else result
