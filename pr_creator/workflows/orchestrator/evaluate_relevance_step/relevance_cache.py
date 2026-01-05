from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from dulwich.repo import Repo

logger = logging.getLogger(__name__)


def default_relevance_cache_path() -> Path:
    """
    Default disk location for relevance caching.

    Keep consistent with other pr-creator home storage (e.g. cursor output logs).
    """
    return Path.home() / ".pr-creator" / "relevance-cache.json"


def compute_prompt_hash(relevance_prompt: str) -> str:
    """
    Compute a stable hash for the relevance prompt.

    Note: per current requirements, we hash ONLY the raw relevance prompt string.
    """
    data = (relevance_prompt or "").encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


def try_get_repo_head_sha(repo_path: Path) -> Optional[str]:
    """
    Best-effort: resolve the current checked-out commit SHA for a git repo.

    Returns:
    - 40-char hex SHA string on success
    - None if repo_path is not a git repo or SHA cannot be resolved
    """
    try:
        repo = Repo.discover(str(repo_path))
        sha = repo.head()
        if not isinstance(sha, (bytes, bytearray)):
            return None
        return bytes(sha).hex()
    except Exception as exc:
        logger.info("Could not resolve HEAD sha for %s: %s", repo_path, exc)
        return None


def _make_cache_key(*, repo_identifier: str, sha: str, prompt_hash: str) -> str:
    # Keep keys simple and human-readable; avoid extra structure beyond the required parts.
    return f"{repo_identifier}::{sha}::{prompt_hash}"


def _load_entries(path: Path) -> Dict[str, bool]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            return {}
        out: Dict[str, bool] = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, bool):
                out[k] = v
        return out
    except Exception as exc:
        logger.warning("Failed to read relevance cache at %s: %s", path, exc)
        return {}


def _atomic_write_json(path: Path, data: Dict[str, bool]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, sort_keys=True, indent=2) + "\n"

    # Atomic replace: write to temp file in same directory and rename over target.
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


@dataclass
class DiskRelevanceCache:
    path: Path = field(default_factory=default_relevance_cache_path)
    _loaded: bool = field(default=False, init=False)
    _entries: Dict[str, bool] = field(default_factory=dict, init=False)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._entries = _load_entries(self.path)
        self._loaded = True

    def get(
        self, *, repo_identifier: str, sha: str, prompt_hash: str
    ) -> Optional[bool]:
        self._ensure_loaded()
        return self._entries.get(
            _make_cache_key(
                repo_identifier=repo_identifier, sha=sha, prompt_hash=prompt_hash
            )
        )

    def set(
        self, *, repo_identifier: str, sha: str, prompt_hash: str, value: bool
    ) -> None:
        self._ensure_loaded()
        key = _make_cache_key(
            repo_identifier=repo_identifier, sha=sha, prompt_hash=prompt_hash
        )
        self._entries[key] = bool(value)
        _atomic_write_json(self.path, self._entries)
