from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class EvaluateAgent(ABC):
    @abstractmethod
    def evaluate(self, repo_path: Path, relevance_prompt: str) -> bool:
        """Return True if the repo is relevant for the given prompt."""
        raise NotImplementedError
