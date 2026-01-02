from __future__ import annotations

import logging
import os
from typing import Mapping

logger = logging.getLogger(__name__)

# Single source of truth for default review retry behavior.
DEFAULT_REVIEW_MAX_ATTEMPTS = 2


def get_review_max_attempts(environ: Mapping[str, str] | None = None) -> int:
    """
    Maximum number of review->apply retries per repo.

    Configured via env var `REVIEW_MAX_ATTEMPTS` (default: DEFAULT_REVIEW_MAX_ATTEMPTS).
    """
    env = environ or os.environ
    raw = (env.get("REVIEW_MAX_ATTEMPTS") or "").strip()
    if not raw:
        return DEFAULT_REVIEW_MAX_ATTEMPTS
    try:
        return max(0, int(raw))
    except Exception:
        logger.warning(
            "Invalid REVIEW_MAX_ATTEMPTS=%r; defaulting to %s",
            raw,
            DEFAULT_REVIEW_MAX_ATTEMPTS,
        )
        return DEFAULT_REVIEW_MAX_ATTEMPTS
