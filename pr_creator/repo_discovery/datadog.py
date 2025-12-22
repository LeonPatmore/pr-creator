from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DATADOG_SITE = "datadoghq.com"


def _extract_repo_urls(service: dict) -> List[str]:
    attrs = service.get("attributes", {})
    integrations = attrs.get("integrations", {}) or {}
    github = integrations.get("github", {}) or {}
    candidates = [
        github.get("url"),
        github.get("repository_url"),
        github.get("repository"),
    ]
    return [c for c in candidates if c]


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

    try:
        from datadog_api_client.v2 import ApiClient, Configuration  # type: ignore
        from datadog_api_client.v2.api.services_api import ServicesApi  # type: ignore
    except ImportError as exc:
        raise ValueError(
            "datadog-api-client is required for Datadog discovery; install it first."
        ) from exc

    config = Configuration()
    config.api_key = {"apiKeyAuth": api_key, "appKeyAuth": app_key}
    config.server_variables["site"] = site.replace("https://", "").replace("api.", "")

    repos: set[str] = set()
    page_size = 200
    page_number = 0

    with ApiClient(config) as client:
        api = ServicesApi(client)
        while True:
            resp = api.list_services(
                filter_team=team,
                page_size=page_size,
                page_number=page_number,
            )
            for service in resp.data or []:
                service_dict = (
                    service.to_dict() if hasattr(service, "to_dict") else service
                )
                for repo_url in _extract_repo_urls(service_dict):
                    repos.add(repo_url)

            data_len = len(resp.data or [])
            total = None
            if resp.meta and getattr(resp.meta, "page", None):
                total = getattr(resp.meta.page, "total_filtered_count", None)

            if data_len < page_size or (
                total is not None and (page_number + 1) * page_size >= total
            ):
                break
            page_number += 1

    logger.info("Datadog discovery for team %s found %d repos", team, len(repos))
    return sorted(repos)
