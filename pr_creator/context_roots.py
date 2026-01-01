from __future__ import annotations

import os
from pathlib import Path


AGENT_CONTEXT_ROOTS_ENV = "AGENT_CONTEXT_ROOTS"


def normalize_context_roots(roots: list[str]) -> list[str]:
    parts = [str(p).strip() for p in roots if str(p).strip()]

    normalized: list[str] = []
    seen: set[str] = set()
    for p in parts:
        try:
            abs_p = str(Path(p).expanduser().resolve())
        except Exception:
            abs_p = p
        if abs_p not in seen:
            normalized.append(abs_p)
            seen.add(abs_p)
    return normalized


def merge_context_roots(*root_lists: list[str]) -> list[str]:
    """
    Merge multiple context-root lists, dedupe, and normalize.

    Order matters: earlier lists win for ordering (and therefore mount indices).
    """
    combined: list[str] = []
    for roots in root_lists:
        combined.extend(list(roots or []))
    return normalize_context_roots(combined)


def get_context_roots_from_env() -> list[str]:
    """
    Host directories to expose to agents as read-only context.

    Preferred env var:
      - AGENT_CONTEXT_ROOTS="/abs/path/one,/abs/path/two"
    """
    raw = os.environ.get(AGENT_CONTEXT_ROOTS_ENV, "").strip()

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return normalize_context_roots(parts)
