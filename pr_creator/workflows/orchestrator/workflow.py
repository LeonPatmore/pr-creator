import logging

from pydantic_graph.beta import GraphBuilder
from pydantic_graph.beta.join import reduce_list_append

from pr_creator.logging_config import ensure_logging_configured
from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.orchestrator.init_step import step as init_step
from pr_creator.workflows.orchestrator.discover_repos_step import step as discover_step
from pr_creator.workflows.orchestrator.evaluate_relevance_step import (
    step as evaluate_step,
)
from pr_creator.workflows.orchestrator.orchestrate_change_step import (
    step as orchestrate_step,
)

logger = logging.getLogger(__name__)


def build_orchestrator_graph() -> GraphBuilder:
    """
    Build orchestrator graph with parallel execution.

    Flow:
    - init_step: Initialize state
    - discover_repos_step: Discover/normalize repo URLs, returns list of repos
    - Map over repos for parallel processing (evaluate → orchestrate)
    - Join all parallel results before ending
    """
    g = GraphBuilder(
        state_type=OrchestratorState,
        output_type=OrchestratorState,
    )

    # Register step functions with the graph
    init_step_node = g.step(init_step.init_step)
    discover_repos_step = g.step(discover_step.discover_repos_step)
    evaluate_relevance_step = g.step(evaluate_step.evaluate_relevance_step)
    orchestrate_change_step = g.step(orchestrate_step.orchestrate_change_step)

    # Join node to collect all parallel results
    collect_results = g.join(reduce_list_append, initial_factory=list)

    # Build flow for repos
    g.add(
        g.edge_from(g.start_node).to(init_step_node),
        g.edge_from(init_step_node).to(discover_repos_step),
        # Map over discovered repos (if any) - empty list gracefully skips
        g.edge_from(discover_repos_step).map().to(evaluate_relevance_step),
        # Edge from evaluate to orchestrate (None values handled in orchestrate step)
        g.edge_from(evaluate_relevance_step).to(orchestrate_change_step),
        # Join all parallel orchestrate results before ending
        g.edge_from(orchestrate_change_step).to(collect_results),
        g.edge_from(collect_results).to(g.end_node),
    )

    return g


async def run_orchestrator_workflow(state: OrchestratorState) -> OrchestratorState:
    """Run the orchestrator workflow with parallel repo processing."""
    ensure_logging_configured()
    graph = build_orchestrator_graph().build()
    await graph.run(state=state)
    # State is mutated during execution, return it
    return state
