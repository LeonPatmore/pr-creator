from __future__ import annotations


def truncate_with_ellipsis(text: str, max_len: int) -> str:
    text = text.strip()
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len].rstrip()
    return text[: max_len - 3].rstrip(" -:") + "..."


def limit_slug(slug: str, max_words: int, max_len: int) -> str:
    parts = [p for p in slug.split("-") if p]
    if max_words > 0:
        parts = parts[:max_words]
    limited = "-".join(parts) if parts else "auto-change"
    if max_len > 0 and len(limited) > max_len:
        limited = limited[:max_len].rstrip("-")
    return limited or "auto-change"


def slugify(text: str) -> str:
    safe = "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe or "auto-change"
