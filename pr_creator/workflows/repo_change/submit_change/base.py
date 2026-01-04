from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional


class SubmitChange(ABC):
    @abstractmethod
    def submit(
        self,
        repo_path: Path,
        change_prompt: str | None = None,
        change_id: str | None = None,
        branch: str | None = None,
    ) -> Optional[Dict[str, str]]:
        """Submit changes for the given repository (e.g., open a PR).

        Args:
            repo_path: Path to the repository
            change_prompt: The prompt that triggered the change (for PR description)
            change_id: Optional change ID for static branch names
            branch: Optional branch name to submit from (will be checked out before committing)

        Returns metadata about a created PR (if any), otherwise None.
        """
        raise NotImplementedError
