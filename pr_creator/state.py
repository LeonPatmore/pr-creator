from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class WorkflowState:
    prompt: str
    relevance_prompt: str
    repos: List[str]
    working_dir: Path
    cloned: Dict[str, Path] = field(default_factory=dict)
    branches: Dict[str, str] = field(default_factory=dict)
    relevant: List[str] = field(default_factory=list)
    processed: List[str] = field(default_factory=list)
    irrelevant: List[str] = field(default_factory=list)
    created_prs: List[Dict[str, str]] = field(default_factory=list)
    datadog_team: Optional[str] = None
    datadog_site: str = "datadoghq.com"
    change_id: Optional[str] = None
