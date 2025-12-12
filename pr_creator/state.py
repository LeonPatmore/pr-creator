from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class WorkflowState:
    prompt: str
    relevance_prompt: str
    repos: List[str]
    working_dir: Path
    cloned: Dict[str, Path] = field(default_factory=dict)
    relevant: List[str] = field(default_factory=list)
    processed: List[str] = field(default_factory=list)

