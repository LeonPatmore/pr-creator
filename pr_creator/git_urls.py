from __future__ import annotations

import urllib.parse
from typing import Optional


def github_slug_from_url(url: str) -> Optional[str]:
    """Extract owner/repo slug from common GitHub HTTPS or SSH URLs."""
    if url.startswith("git@github.com:"):
        return url.removeprefix("git@github.com:").removesuffix(".git")

    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.endswith("github.com") and parsed.path:
        return parsed.path.lstrip("/").removesuffix(".git")

    return None


def token_auth_github_url(url: str, token: str) -> Optional[str]:
    """Return HTTPS URL with embedded token for GitHub operations."""
    slug = github_slug_from_url(url)
    if not slug:
        return None
    encoded = urllib.parse.quote(token, safe="")
    return f"https://{encoded}:x-oauth-basic@github.com/{slug}.git"


def normalize_repo_identifier(repo: str, default_org: Optional[str]) -> str:
    """
    Normalize repo identifiers to a GitHub HTTPS URL.
    Accepts:
    - Full URLs (returned unchanged)
    - owner/repo slugs
    - repo names (requires default_org)
    """
    repo = repo.strip()
    if not repo:
        raise ValueError("Empty repository identifier provided")

    if repo.startswith(("http://", "https://", "git@")):
        return repo

    # owner/repo form
    if "/" in repo:
        slug = repo.removeprefix("/").removesuffix("/").removesuffix(".git")
        return f"https://github.com/{slug}.git"

    # repo name only, need default org
    if not default_org:
        raise ValueError(
            "Repository name provided without owner; set GITHUB_DEFAULT_ORG to supply the owner"
        )
    slug = f"{default_org.rstrip('/')}/{repo.removesuffix('.git')}"
    return f"https://github.com/{slug}.git"
