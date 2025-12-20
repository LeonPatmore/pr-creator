from __future__ import annotations

import logging
import os
from typing import Optional


def configure_logging(level: Optional[str] = None, force: bool = False) -> None:
    """Configure root logging with a standard format.

    If level is None, uses LOG_LEVEL env var or INFO.
    """
    resolved = level or os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, resolved.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=force,
    )


def ensure_logging_configured(level: Optional[str] = None) -> None:
    """Configure logging only if no handlers are present."""
    if logging.getLogger().handlers:
        return
    configure_logging(level=level, force=False)

