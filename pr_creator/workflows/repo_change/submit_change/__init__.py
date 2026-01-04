from __future__ import annotations

import os

from .base import SubmitChange
from .github_submitter import GithubSubmitter

DEFAULT_SUBMITTER = "github"


def get_submitter(name: str | None = None) -> SubmitChange:
    submitter_name = (
        name or os.environ.get("SUBMIT_CHANGE") or DEFAULT_SUBMITTER
    ).lower()
    if submitter_name == "github":
        return GithubSubmitter()
    raise ValueError(f"Unknown submitter: {submitter_name}")


__all__ = ["SubmitChange", "GithubSubmitter", "get_submitter"]
