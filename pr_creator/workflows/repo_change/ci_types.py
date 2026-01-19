from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CiFailure:
    pr_url: str
    head_sha: str
    name: str
    details_url: str | None
    logs: str
