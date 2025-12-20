from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import pytest
from github import Github


def _parse_slug(repo_url: str) -> Optional[str]:
    cleaned = repo_url.rstrip("/")
    cleaned = cleaned.removesuffix(".git")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        owner = parts[-2]
        name = parts[-1]
        return f"{owner}/{name}"
    return None


@pytest.mark.integration
def test_cli_creates_pr_and_cleans_up() -> None:
    required_env = ["GITHUB_TOKEN", "CURSOR_API_KEY"]
    missing = [k for k in required_env if not os.environ.get(k)]
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")

    repo_url = os.environ.get("TEST_REPO_URL", "https://github.com/LeonPatmore/cheap-ai-agents-aws")
    slug = _parse_slug(repo_url)
    if not slug:
        pytest.skip(f"Could not parse owner/repo from TEST_REPO_URL: {repo_url}")

    token = os.environ["GITHUB_TOKEN"]
    gh = Github(token)
    repo = gh.get_repo(slug)

    marker = f"TEST_MARKER_{uuid.uuid4().hex[:8]}"
    branch_prefix = f"auto/pr-test-{uuid.uuid4().hex[:8]}"

    env = os.environ.copy()
    env.update(
        {
            "SUBMIT_BRANCH_PREFIX": branch_prefix,
            "SUBMIT_PR_TITLE": f"Automated test PR {marker}",
            "SUBMIT_PR_BODY": f"Automated test body {marker}",
        }
    )

    project_root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            sys.executable,
            "-m",
            "pr_creator.cli",
            "--prompt",
            f"Append to README: {marker}",
            "--relevance-prompt",
            "Any repo",
            "--repo",
            repo_url,
            "--working-dir",
            tmpdir,
            "--log-level",
            "INFO",
        ]
        subprocess.run(cmd, check=True, cwd=project_root, env=env)

    # Find the PR created on the branch that starts with our prefix.
    prs = [pr for pr in repo.get_pulls(state="open") if pr.head.ref.startswith(branch_prefix)]
    assert prs, f"Expected an open PR with branch prefix {branch_prefix}"
    pr = prs[0]
    branch_ref = pr.head.ref

    # Cleanup: close PR and delete branch
    pr.edit(state="closed")
    try:
        ref = repo.get_git_ref(f"heads/{branch_ref}")
        ref.delete()
    except Exception:
        # Ignore cleanup errors; test already validated the PR existed.
        pass

