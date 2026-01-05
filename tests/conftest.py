from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv


def pytest_configure(config) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    dotenv_path = repo_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)
