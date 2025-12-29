from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple

import pytest
import docker
from github import Auth, Github


def _parse_owner_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    cleaned = repo_url.rstrip("/").removesuffix(".git")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None


def _docker_available() -> bool:
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _run_cli_and_assert_pr(
    repo_arg: str, repo_slug: str, env: dict, branch_prefix: str
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
            "--working-dir",
            tmpdir,
            "--log-level",
            "INFO",
        ]
        subprocess.run(cmd, check=True, cwd=project_root, env=env)

    prs = [
        pr
        for pr in repo.get_pulls(state="open")
        if pr.head.ref.startswith(branch_prefix)
    ]
    assert prs, f"Expected an open PR with branch prefix {branch_prefix}"
    pr = prs[0]
    branch_ref = pr.head.ref

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
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")
    if not _docker_available():
        pytest.skip("Docker is not available; skipping CLI e2e")

    repo_url = os.environ.get(
        "TEST_REPO_URL", "https://github.com/LeonPatmore/cheap-ai-agents-aws"
    )
    parsed = _parse_owner_repo(repo_url)
    if not parsed:
        pytest.skip(f"Could not parse owner/repo from TEST_REPO_URL: {repo_url}")
    owner, name = parsed
    slug = f"{owner}/{name}"

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

    if use_repo_name_only:
        env["GITHUB_DEFAULT_ORG"] = owner
        repo_arg = name  # owner supplied via env
    else:
        env.pop("GITHUB_DEFAULT_ORG", None)
        repo_arg = repo_url

    _run_cli_and_assert_pr(repo_arg, slug, env, branch_prefix)
