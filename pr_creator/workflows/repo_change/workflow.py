import logging

from pydantic_graph import Graph

from pr_creator.logging_config import ensure_logging_configured
from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.steps import (
    ApplyChanges,
    CleanupRepo,
    GenerateNames,
    ReviewChanges,
    SubmitChanges,
    WaitForActions,
    WorkspaceRepo,
)

logger = logging.getLogger(__name__)


def build_repo_change_single_repo_graph() -> Graph:
    """
    A repo-change graph that operates on a *single* repo, assuming the prompt is already set.
    Intended to be invoked by the orchestrator workflow.
    """
    return Graph(
        nodes=[
            GenerateNames,
            WorkspaceRepo,
            ApplyChanges,
            ReviewChanges,
            SubmitChanges,
            WaitForActions,
            CleanupRepo,
        ],
        state_type=RepoChangeState,
    )


async def run_repo_change_for_repo(
    state: RepoChangeState, *, repo_url: str
) -> RepoChangeState:
    ensure_logging_configured()
    graph = build_repo_change_single_repo_graph()
    # Start directly at naming for the specific repo.
    result = await graph.run(start_node=GenerateNames(repo_url=repo_url), state=state)
    return result.state if hasattr(result, "state") else result
