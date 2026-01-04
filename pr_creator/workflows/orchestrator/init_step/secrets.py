from __future__ import annotations

from typing import Mapping


def build_change_agent_secrets(
    *,
    secret_kv_pairs: list[str] | None,
    secret_env_keys: list[str] | None,
    environ: Mapping[str, str],
) -> dict[str, str]:
    """
    Build a dict of env vars (often secrets) to forward into the change agent.

    - secret_kv_pairs: items like "KEY=VALUE"
    - secret_env_keys: items like "KEY" (value read from environ)

    If the same key is provided multiple times, the last value wins.
    """
    out: dict[str, str] = {}

    for item in secret_kv_pairs or []:
        if "=" not in item:
            raise ValueError(f"Invalid --secret value (expected KEY=VALUE): {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --secret value (empty KEY): {item!r}")
        out[key] = value

    for key in secret_env_keys or []:
        k = key.strip()
        if not k:
            raise ValueError("Invalid --secret-env value (empty KEY)")
        if k not in environ:
            raise ValueError(f"Missing environment variable for --secret-env: {k}")
        out[k] = environ[k]

    return out
