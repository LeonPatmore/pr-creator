from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar, Tuple, Type

logger = logging.getLogger(__name__)

T = TypeVar("T")


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
