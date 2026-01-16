from __future__ import annotations

import asyncio
import os


def _max_parallel_repos_from_env() -> int:
    try:
        value = int(os.environ.get("MAX_PARALLEL_REPOS", "3").strip())
        return max(1, value)
    except Exception:
        return 3


MAX_PARALLEL_REPOS = _max_parallel_repos_from_env()
CONCURRENCY_SEMAPHORE = asyncio.Semaphore(MAX_PARALLEL_REPOS)
