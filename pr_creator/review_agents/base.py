from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ReviewAgent(ABC):
    @abstractmethod
    def review(
        self,
        repo_path: Path,
        *,
        context_roots: list[str],
        task_prompt: str | None = None,
        secrets: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        """
        Review the repo's uncommitted state.

        Returns:
        - (needs_changes, feedback)
        - feedback should be a concise set of required changes when needs_changes=True,
          otherwise None.
        """
        raise NotImplementedError
