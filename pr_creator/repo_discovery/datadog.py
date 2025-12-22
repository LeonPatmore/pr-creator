from __future__ import annotations

import logging
from typing import List, Optional

from datadog_api_client.v2 import ApiClient, Configuration
from datadog_api_client.v2.api.service_definition_api import ServiceDefinitionApi

logger = logging.getLogger(__name__)

DEFAULT_DATADOG_SITE = "datadoghq.com"


def _extract_repo_urls(service: dict) -> List[str]:
    attrs = service.get("attributes", {})
    schema = attrs.get("schema", {}) or {}

    integrations = attrs.get("integrations", {}) or {}
    github = integrations.get("github", {}) or {}

    candidates = [
        github.get("url"),
        github.get("repository_url"),
        github.get("repository"),
    ]

    # Service Catalog definitions expose repositories via the schema.
    repos = schema.get("repos", []) or attrs.get("repos", []) or []
    for repo in repos:
        if isinstance(repo, dict):
            candidates.append(repo.get("url"))

    return [c for c in candidates if c]


def _service_matches_team(service: dict, team: str) -> bool:
    """Datadog Service Catalog service has the team on the schema."""
    attrs = service.get("attributes", {}) or {}
    schema = attrs.get("schema", {}) or {}

    candidates = [
        attrs.get("team"),
        attrs.get("dd_team"),
        attrs.get("dd-team"),
        schema.get("team"),
        schema.get("dd_team"),
        schema.get("dd-team"),
    ]

    return any(
        isinstance(value, str) and value.lower() == team.lower() for value in candidates
    )


def discover_repos_from_datadog(
    team: str,
    api_key: Optional[str],
    app_key: Optional[str],
    site: str = DEFAULT_DATADOG_SITE,
) -> List[str]:
    if not api_key or not app_key:
        raise ValueError(
            "DATADOG_API_KEY and DATADOG_APP_KEY are required for discovery"
        )

    config = Configuration()
    config.api_key = {"apiKeyAuth": api_key, "appKeyAuth": app_key}
    config.server_variables["site"] = site.replace("https://", "").replace("api.", "")

    repos: set[str] = set()
    page_size = 100

    with ApiClient(config) as client:
        api = ServiceDefinitionApi(client)
        for service in api.list_service_definitions_with_pagination(
            page_size=page_size
        ):
            service_dict = service.to_dict() if hasattr(service, "to_dict") else service
            if not isinstance(service_dict, dict):
                continue
            if not _service_matches_team(service_dict, team):
                continue
            for repo_url in _extract_repo_urls(service_dict):
                repos.add(repo_url)

    logger.info("Datadog discovery for team %s found %d repos", team, len(repos))
    return sorted(repos)
