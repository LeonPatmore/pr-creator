from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class OrchestratorState:
    """
    Orchestrator workflow state.

    This workflow is responsible for:
    - loading the base prompt (Jira/prompt-config/CLI)
    - discovering repos
    - for each repo, planning a repo-specific prompt (AI)
    - invoking the repo-change workflow for that repo
    """

    # Base prompts / inputs
    prompt: str
    relevance_prompt: str
    repos: List[str]
    working_dir: Path

    cli_prompt: Optional[str] = None
    prompt_config_owner: Optional[str] = None
    prompt_config_repo: Optional[str] = None
    prompt_config_ref: Optional[str] = None
    prompt_config_path: Optional[str] = None

    jira_ticket: Optional[str] = None
    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None

    context_roots: List[str] = field(default_factory=list)

    change_agent_secrets: Dict[str, str] = field(default_factory=dict)
    change_agent_secret_kv_pairs: List[str] = field(default_factory=list)
    change_agent_secret_env_keys: List[str] = field(default_factory=list)

    datadog_team: Optional[str] = None
    datadog_site: str = "datadoghq.com"

    # Stable branch naming / rollout id (propagated to repo-change workflow)
    change_id: Optional[str] = None

    # Orchestrator outputs
    repo_prompts: Dict[str, str] = field(default_factory=dict)
    planning_clones: Dict[str, Path] = field(default_factory=dict)

    # Rollup outputs from repo-change runs
    created_prs: List[Dict[str, str]] = field(default_factory=list)
    irrelevant: List[str] = field(default_factory=list)
