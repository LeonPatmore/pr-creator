from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv


def pytest_configure(config) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    # Ensure the real package root is importable even when tests mirror the
    # pr_creator module structure under tests/.
    sys.path.insert(0, str(repo_root))
    dotenv_path = repo_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)
