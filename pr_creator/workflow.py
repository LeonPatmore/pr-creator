import logging
import os
from pydantic_graph import Graph
from .logging_config import ensure_logging_configured
from .secrets import build_change_agent_secrets
from .state import WorkflowState
from pr_creator.context_roots import get_context_roots_from_env, merge_context_roots
from .steps import (
    ApplyChanges,
    CleanupRepo,
    DiscoverRepos,
    EvaluateRelevance,
    GenerateNames,
    NextRepo,
    SubmitChanges,
    WorkspaceRepo,
)

logger = logging.getLogger(__name__)


def build_graph() -> Graph:
    return Graph(
        nodes=[
            DiscoverRepos,
            NextRepo,
            GenerateNames,
            WorkspaceRepo,
            EvaluateRelevance,
            ApplyChanges,
            SubmitChanges,
            CleanupRepo,
        ],
        state_type=WorkflowState,
    )


async def run_workflow(state: WorkflowState) -> WorkflowState:
    ensure_logging_configured()

    # Resolve secrets early so all downstream steps get a consistent view.
    if state.change_agent_secret_kv_pairs or state.change_agent_secret_env_keys:
        resolved = build_change_agent_secrets(
            secret_kv_pairs=state.change_agent_secret_kv_pairs,
            secret_env_keys=state.change_agent_secret_env_keys,
            environ=os.environ,
        )
        # Explicit secrets provided on state override derived values.
        state.change_agent_secrets = {**resolved, **state.change_agent_secrets}

    state.context_roots = merge_context_roots(
        state.context_roots, get_context_roots_from_env()
    )

    graph = build_graph()
    result = await graph.run(start_node=DiscoverRepos(), state=state)
    return result.state if hasattr(result, "state") else result
