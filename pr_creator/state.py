from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class WorkflowState:
    prompt: str
    relevance_prompt: str
    repos: List[str]
    working_dir: Path
    context_roots: List[str] = field(default_factory=list)
    # Extra env vars (often secrets) forwarded to the change agent process/container.
    # Values should never be logged.
    change_agent_secrets: Dict[str, str] = field(default_factory=dict)
    # Raw secret inputs (e.g. from CLI) that are resolved into `change_agent_secrets`
    # during workflow setup.
    change_agent_secret_kv_pairs: List[str] = field(default_factory=list)
    change_agent_secret_env_keys: List[str] = field(default_factory=list)
    cloned: Dict[str, Path] = field(default_factory=dict)
    branches: Dict[str, str] = field(default_factory=dict)
    pr_titles: Dict[str, str] = field(default_factory=dict)
    commit_messages: Dict[str, str] = field(default_factory=dict)
    relevant: List[str] = field(default_factory=list)
    processed: List[str] = field(default_factory=list)
    irrelevant: List[str] = field(default_factory=list)
    created_prs: List[Dict[str, str]] = field(default_factory=list)
    datadog_team: Optional[str] = None
    datadog_site: str = "datadoghq.com"
    change_id: Optional[str] = None
