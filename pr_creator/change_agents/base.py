from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ChangeAgent(ABC):
    @abstractmethod
    def run(
        self,
        repo_path: Path,
        prompt: str,
        *,
        context_roots: list[str],
        secrets: dict[str, str] | None = None,
    ) -> None:
        """Apply changes to the given repo."""
        raise NotImplementedError
