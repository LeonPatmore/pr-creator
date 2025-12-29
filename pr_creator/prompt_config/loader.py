from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import yaml
from github import Auth, Github
from github.GithubException import GithubException

logger = logging.getLogger(__name__)


def _load_yaml_from_github(
    owner: str, repo_name: str, ref: str, path: str, token: Optional[str]
) -> Dict[str, Any]:
    if not token:
        logger.warning("GITHUB_TOKEN not set; cannot load private GitHub config")
        return {}
    repo_slug = f"{owner}/{repo_name}"
    gh = Github(auth=Auth.Token(token))
    try:
        repo = gh.get_repo(repo_slug)
        content_file = repo.get_contents(path, ref=ref)
        return yaml.safe_load(content_file.decoded_content) or {}
    except GithubException as exc:
        logger.warning("Failed to fetch config via GitHub API: %s", exc)
        return {}


def load_prompts_from_config(
    owner: str, repo: str, ref: str, path: str, token: Optional[str]
) -> Dict[str, str]:
    """
    Load change/relevance prompts from a YAML config in GitHub.
    Requires owner/repo/ref/path and uses the GitHub API (works with private repos).
    """
    data: Dict[str, Any] = _load_yaml_from_github(owner, repo, ref, path, token)
    change_prompt = data.get("change_prompt") or data.get("prompt")
    relevance_prompt = data.get("relevance_prompt")
    change_id = data.get("change_id")
    if not change_prompt or not relevance_prompt:
        raise ValueError(
            "Prompt config YAML must include change_prompt and relevance_prompt"
        )
    logger.info(
        "Loaded prompt config from %s/%s@%s:%s (change_prompt len=%s, relevance_prompt len=%s%s)",
        owner,
        repo,
        ref,
        path,
        len(str(change_prompt)),
        len(str(relevance_prompt)),
        f", change_id={change_id}" if change_id else "",
    )
    result = {"prompt": str(change_prompt), "relevance_prompt": str(relevance_prompt)}
    if change_id:
        result["change_id"] = str(change_id)
    return result
