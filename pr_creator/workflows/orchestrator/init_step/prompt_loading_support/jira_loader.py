from __future__ import annotations

import logging
import os
from typing import Dict, Optional

from jira import JIRA

logger = logging.getLogger(__name__)


def load_prompt_from_jira(
    base_url: Optional[str],
    ticket_id: str,
    email: Optional[str],
    api_token: Optional[str],
    timeout: int = 20,
) -> Dict[str, str]:
    """
    Fetch a Jira ticket and return a prompt built from its summary + description.
    The change_id is set to the Jira ticket id for stable branch naming.
    """
    resolved_base = base_url or os.environ.get("JIRA_BASE_URL")
    resolved_email = email or os.environ.get("JIRA_EMAIL")
    resolved_token = api_token or os.environ.get("JIRA_API_TOKEN")

    if not resolved_base:
        raise ValueError("Jira base URL is required when loading prompt from Jira")
    if resolved_token and not resolved_email:
        raise ValueError("Jira email is required when using an API token")

    normalized_base = resolved_base.rstrip("/")
    if not normalized_base.startswith("http"):
        normalized_base = f"https://{normalized_base.lstrip('/')}"

    logger.info("Fetching Jira ticket %s from %s", ticket_id, normalized_base)
    jira_client = JIRA(
        server=normalized_base,
        basic_auth=(resolved_email or "", resolved_token or ""),
        options={"rest_api_version": "3"},
        timeout=timeout,
    )

    issue = jira_client.issue(
        ticket_id, fields="summary,description", expand="renderedFields"
    )
    fields = getattr(issue, "fields", None)
    summary = getattr(fields, "summary", "") if fields else ""
    raw_description = getattr(fields, "description", None) if fields else None
    rendered_description = (
        (getattr(issue, "raw", {}) or {}).get("renderedFields", {}).get("description")
    )

    description_text = ""
    if rendered_description:
        description_text = str(rendered_description).strip()
    elif raw_description:
        description_text = str(raw_description).strip()

    prompt_parts = [part for part in (summary, description_text) if part]
    if not prompt_parts:
        raise ValueError(
            f"Jira ticket {ticket_id} is missing summary/description for prompt."
        )

    prompt = "\n\n".join(prompt_parts).strip()
    logger.info("Loaded prompt from Jira ticket %s (len=%s)", ticket_id, len(prompt))
    return {"prompt": prompt, "change_id": ticket_id}
