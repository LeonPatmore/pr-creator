from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional


class SubmitChange(ABC):
    @abstractmethod
    def submit(self, repo_path: Path) -> Optional[Dict[str, str]]:
        """Submit changes for the given repository (e.g., open a PR).

        Returns metadata about a created PR (if any), otherwise None.
        """
        raise NotImplementedError
