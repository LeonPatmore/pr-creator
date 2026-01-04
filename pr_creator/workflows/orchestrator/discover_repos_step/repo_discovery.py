from __future__ import annotations

import os

from pr_creator.git_urls import normalize_repo_identifier
from pr_creator.workflows.orchestrator.discover_repos_step.datadog import (
    discover_repos_from_datadog,
)


def resolve_and_normalize_repos(
    repos: list[str], *, datadog_team: str | None, datadog_site: str
) -> list[str]:
    combined = list(repos)
    default_org = os.environ.get("GITHUB_DEFAULT_ORG")

    if datadog_team:
        dd_api = os.environ.get("DATADOG_API_KEY")
        dd_app = os.environ.get("DATADOG_APP_KEY")
        discovered = discover_repos_from_datadog(
            datadog_team, dd_api, dd_app, datadog_site
        )
        combined.extend(discovered)

    seen = set()
    deduped: list[str] = []
    for r in combined:
        if r not in seen:
            deduped.append(r)
            seen.add(r)

    normalized: list[str] = [normalize_repo_identifier(r, default_org) for r in deduped]

    seen_norm = set()
    out: list[str] = []
    for r in normalized:
        if r not in seen_norm:
            out.append(r)
            seen_norm.add(r)

    if not out:
        raise ValueError("No repositories provided or discovered; cannot proceed.")
    return out
