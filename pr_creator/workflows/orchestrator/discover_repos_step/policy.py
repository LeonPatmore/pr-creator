from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverReposPolicyResult:
    parallel_inputs: list[str | None]
    log_level: int
    log_message: str | None = None


def choose_parallel_inputs(
    *, repos: list[str], has_mcp_config: bool
) -> DiscoverReposPolicyResult:
    """
    Decide what the orchestrator should process in parallel based on discovery results.

    When no repos are discovered:
    - If MCP is configured, return [None] so downstream can run a "no-repo" prompt.
    - Otherwise return [] to skip processing.
    """
    if repos:
        return DiscoverReposPolicyResult(
            parallel_inputs=repos,
            log_level=20,  # logging.INFO
            log_message=f"[orchestrator] discovered {len(repos)} repos for parallel processing",
        )

    if has_mcp_config:
        return DiscoverReposPolicyResult(
            parallel_inputs=[None],
            log_level=20,  # logging.INFO
            log_message=(
                "[orchestrator] no repositories discovered; running orchestrator with no-repo prompt"
            ),
        )

    return DiscoverReposPolicyResult(
        parallel_inputs=[],
        log_level=30,  # logging.WARNING
        log_message=(
            "No repositories provided and no MCP config specified. "
            "The orchestrator will skip processing. "
            "Consider providing --repo, --datadog-team, or --mcp-config."
        ),
    )
