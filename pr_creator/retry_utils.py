from __future__ import annotations

import logging
import os
import time
from typing import Callable, TypeVar, Tuple, Type

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig:
    """
    Configurable retry settings with exponential backoff.

    Args:
        env_prefix: Prefix for environment variable names (e.g., "APPLY", "NAMING")
        default_max_attempts: Default number of retry attempts
        default_backoff_base: Default exponential backoff base
        default_backoff_min: Default minimum backoff time in seconds
        default_backoff_max: Default maximum backoff time in seconds
    """

    def __init__(
        self,
        env_prefix: str,
        default_max_attempts: int = 4,
        default_backoff_base: float = 3.0,
        default_backoff_min: float = 5.0,
        default_backoff_max: float = 60.0,
    ):
        self.env_prefix = env_prefix
        self.default_max_attempts = default_max_attempts
        self.default_backoff_base = default_backoff_base
        self.default_backoff_min = default_backoff_min
        self.default_backoff_max = default_backoff_max

    def get_max_attempts(self) -> int:
        """Get max attempts from environment or default."""
        try:
            return int(
                os.environ.get(
                    f"{self.env_prefix}_MAX_ATTEMPTS", str(self.default_max_attempts)
                ).strip()
            )
        except Exception:
            return self.default_max_attempts

    def get_backoff_base(self) -> float:
        """Get backoff base from environment or default."""
        try:
            return float(
                os.environ.get(
                    f"{self.env_prefix}_BACKOFF_BASE",
                    str(self.default_backoff_base),
                ).strip()
            )
        except Exception:
            return self.default_backoff_base

    def get_backoff_min(self) -> float:
        """Get minimum backoff time from environment or default."""
        try:
            return float(
                os.environ.get(
                    f"{self.env_prefix}_BACKOFF_MIN", str(self.default_backoff_min)
                ).strip()
            )
        except Exception:
            return self.default_backoff_min

    def get_backoff_max(self) -> float:
        """Get maximum backoff time from environment or default."""
        try:
            return float(
                os.environ.get(
                    f"{self.env_prefix}_BACKOFF_MAX", str(self.default_backoff_max)
                ).strip()
            )
        except Exception:
            return self.default_backoff_max

    def calculate_backoff(self, attempt: int) -> float:
        """
        Calculate backoff time with exponential backoff, starting from min.

        Args:
            attempt: The current attempt number (0-indexed)

        Returns:
            Backoff time in seconds

        Examples:
            >>> config = RetryConfig("TEST", default_backoff_base=3.0, default_backoff_min=5.0)
            >>> config.calculate_backoff(0)  # 5 * 3^0 = 5
            5.0
            >>> config.calculate_backoff(1)  # 5 * 3^1 = 15
            15.0
            >>> config.calculate_backoff(2)  # 5 * 3^2 = 45
            45.0
            >>> config.calculate_backoff(3)  # 5 * 3^3 = 135, clamped to max 60.0
            60.0
        """
        base = self.get_backoff_base()
        min_seconds = self.get_backoff_min()
        max_seconds = self.get_backoff_max()

        # Exponential backoff: min * (base^attempt)
        backoff = min_seconds * (base**attempt)

        # Clamp to max
        return min(backoff, max_seconds)


def retry_on_exception(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    log_prefix: str = "",
    **kwargs,
) -> T:
    last_error = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_error = e
            if attempt < max_retries - 1:
                backoff = backoff_base**attempt
                error_msg = str(e)
                if hasattr(e, "reason"):
                    error_msg = str(e.reason)
                logger.warning(
                    "%sretrying after error: %s (attempt %d/%d, backoff=%ss)",
                    f"{log_prefix} " if log_prefix else "",
                    error_msg,
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                time.sleep(backoff)
            else:
                error_msg = str(e)
                if hasattr(e, "reason"):
                    error_msg = str(e.reason)
                logger.error(
                    "%sfailed after %d attempts: %s",
                    f"{log_prefix} " if log_prefix else "",
                    max_retries,
                    error_msg,
                )

    raise last_error
