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
