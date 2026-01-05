from __future__ import annotations

from functools import lru_cache

from github import Auth, Github


@lru_cache(maxsize=8)
def _github_for_token(token: str) -> Github:
    """
    Return a cached GitHub API client for the given token.

    This avoids re-creating the (expensive) Github service object on every iteration
    when workflows loop over repos.
    """
    return Github(auth=Auth.Token(token))


def get_github_client(token: str | None) -> Github | None:
    if not token:
        return None
    return _github_for_token(token)
