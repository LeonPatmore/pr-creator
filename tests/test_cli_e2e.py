from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple

import pytest
from github import Auth, Github


def _parse_owner_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    cleaned = repo_url.rstrip("/").removesuffix(".git")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None


def _run_cli_and_assert_pr(
    repo_arg: str, repo_slug: str, env: dict, change_id: str
) -> None:
    token = env["GITHUB_TOKEN"]
    gh = Github(auth=Auth.Token(token))
    repo = gh.get_repo(repo_slug)

    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            sys.executable,
            "-m",
            "pr_creator.cli",
            "--prompt-config-owner",
            "LeonPatmore",
            "--prompt-config-repo",
            "pr-creator",
            "--prompt-config-ref",
            "main",
            "--prompt-config-path",
            "examples/prompt-config.yaml",
            "--repo",
            repo_arg,
            "--change-id",
            change_id,
            "--working-dir",
            tmpdir,
            "--log-level",
            "INFO",
        ]
        subprocess.run(cmd, check=True, cwd=project_root, env=env)

    prs = list(repo.get_pulls(state="open"))
    assert prs, "Expected an open PR"
    pr = prs[0]
    branch_ref = pr.head.ref
    assert change_id in branch_ref, f"Expected change_id in branch name ({branch_ref})"
    assert (
        pr.title and len(pr.title) <= 60
    ), f"Expected short PR title (got: {pr.title})"

    pr.edit(state="closed")
    try:
        ref = repo.get_git_ref(f"heads/{branch_ref}")
        ref.delete()
    except Exception:
        pass


@pytest.mark.parametrize("use_repo_name_only", [False, True])
def test_cli_creates_pr_and_cleans_up(use_repo_name_only: bool) -> None:
    required_env = ["GITHUB_TOKEN", "CURSOR_API_KEY"]
    missing = [k for k in required_env if not os.environ.get(k)]
    assert not missing, f"Missing required env vars: {', '.join(missing)}"

    repo_url = os.environ.get(
        "TEST_REPO_URL", "https://github.com/LeonPatmore/cheap-ai-agents-aws"
    )
    parsed = _parse_owner_repo(repo_url)
    if not parsed:
        pytest.skip(f"Could not parse owner/repo from TEST_REPO_URL: {repo_url}")
    owner, name = parsed
    slug = f"{owner}/{name}"

    marker = f"TEST_MARKER_{uuid.uuid4().hex[:8]}"
    change_id = f"TEST-{uuid.uuid4().int % (10**10):010d}"

    env = os.environ.copy()
    env.update(
        {
            "SUBMIT_PR_BODY": f"Automated test body {marker}",
        }
    )

    if use_repo_name_only:
        env["GITHUB_DEFAULT_ORG"] = owner
        repo_arg = name  # owner supplied via env
    else:
        env.pop("GITHUB_DEFAULT_ORG", None)
        repo_arg = repo_url

    _run_cli_and_assert_pr(repo_arg, slug, env, change_id)
