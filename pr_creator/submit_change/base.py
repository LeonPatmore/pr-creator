from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SubmitChange(ABC):
    @abstractmethod
    def submit(self, repo_path: Path) -> None:
        """Submit changes for the given repository (e.g., open a PR)."""
        raise NotImplementedError
