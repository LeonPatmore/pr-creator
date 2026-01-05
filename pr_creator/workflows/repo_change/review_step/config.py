from __future__ import annotations

import os

DEFAULT_REVIEW_MAX_ATTEMPTS = 2


def get_review_max_attempts() -> int:
    try:
        return int(
            os.environ.get(
                "REVIEW_MAX_ATTEMPTS", str(DEFAULT_REVIEW_MAX_ATTEMPTS)
            ).strip()
        )
    except Exception:
        return DEFAULT_REVIEW_MAX_ATTEMPTS
