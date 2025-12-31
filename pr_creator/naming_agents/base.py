from __future__ import annotations

from abc import ABC, abstractmethod


class NamingAgent(ABC):
    @abstractmethod
    def generate_short_desc(self, prompt: str) -> str:
        """Generate a short description from the prompt."""
        raise NotImplementedError
