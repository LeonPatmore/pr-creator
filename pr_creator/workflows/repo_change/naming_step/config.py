from __future__ import annotations

import os

DEFAULT_NAMING_MAX_ATTEMPTS = 3


def get_naming_max_attempts() -> int:
    try:
        return int(
            os.environ.get(
                "NAMING_MAX_ATTEMPTS", str(DEFAULT_NAMING_MAX_ATTEMPTS)
            ).strip()
        )
    except Exception:
        return DEFAULT_NAMING_MAX_ATTEMPTS
