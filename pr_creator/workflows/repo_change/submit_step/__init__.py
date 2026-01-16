import os
from functools import lru_cache

from .base import SubmitChange
from .github_submitter import GithubSubmitter

DEFAULT_SUBMITTER = "github"


@lru_cache(maxsize=16)
def _get_submitter_cached(
    submitter_name: str, github_token: str | None
) -> SubmitChange:
    if submitter_name == "github":
        return GithubSubmitter(github_token=github_token)
    raise ValueError(f"Unknown submitter: {submitter_name}")


def get_submitter(
    name: str | None = None, *, github_token: str | None = None
) -> SubmitChange:
    submitter_name = (
        name or os.environ.get("SUBMIT_CHANGE") or DEFAULT_SUBMITTER
    ).lower()
    return _get_submitter_cached(submitter_name, github_token)
