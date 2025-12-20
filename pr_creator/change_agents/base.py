from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ChangeAgent(ABC):
    @abstractmethod
    def run(self, repo_path: Path, prompt: str) -> None:
        """Apply changes to the given repo."""
        raise NotImplementedError

