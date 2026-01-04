import logging

from pydantic_graph import Graph

from pr_creator.logging_config import ensure_logging_configured
from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.orchestrator.discover_repos_step.node import (
    DiscoverReposOrchestrator,
)
from pr_creator.workflows.orchestrator.evaluate_relevance_step.node import (
    EvaluateRelevanceOrchestrator,
)
from pr_creator.workflows.orchestrator.init_step.node import InitOrchestrator
from pr_creator.workflows.orchestrator.next_repo_step.node import NextRepoOrchestrator
from pr_creator.workflows.orchestrator.orchestrate_change_step.node import (
    OrchestrateChange,
)

logger = logging.getLogger(__name__)


def build_orchestrator_graph() -> Graph:
    return Graph(
        nodes=[
            InitOrchestrator,
            DiscoverReposOrchestrator,
            NextRepoOrchestrator,
            EvaluateRelevanceOrchestrator,
            OrchestrateChange,
        ],
        state_type=OrchestratorState,
    )


async def run_orchestrator_workflow(state: OrchestratorState) -> OrchestratorState:
    ensure_logging_configured()
    graph = build_orchestrator_graph()
    result = await graph.run(start_node=InitOrchestrator(), state=state)
    return result.state if hasattr(result, "state") else result
