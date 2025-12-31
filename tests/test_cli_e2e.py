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


def _run_cli_twice_and_assert_two_commits(
    repo_arg: str,
    repo_slug: str,
    env: dict,
    change_id: str,
    prompt_one: str,
    prompt_two: str,
) -> None:
    token = env["GITHUB_TOKEN"]
    gh = Github(auth=Auth.Token(token))
    repo = gh.get_repo(repo_slug)

    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmpdir:
        base_cmd = [
            sys.executable,
            "-m",
            "pr_creator.cli",
            "--repo",
            repo_arg,
            "--change-id",
            change_id,
            "--working-dir",
            tmpdir,
            "--log-level",
            "INFO",
        ]
        for prompt in (prompt_one, prompt_two):
            cmd = base_cmd + ["--prompt", prompt]
            subprocess.run(cmd, check=True, cwd=project_root, env=env)

    pr = None
    for candidate in repo.get_pulls(state="open"):
        if change_id in candidate.head.ref:
            pr = candidate
            break
    assert pr, "Expected an open PR after two runs"

    commit_count = pr.get_commits().totalCount
    assert commit_count >= 2, f"Expected at least two commits, got {commit_count}"

    pr.edit(state="closed")
    try:
        ref = repo.get_git_ref(f"heads/{pr.head.ref}")
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


def test_cli_reuses_workspace_and_creates_two_commits() -> None:
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

    marker = uuid.uuid4().hex[:8]
    change_id = f"TEST-REUSE-{marker}"
    prompt_one = f"Append marker {marker}-one to README first line"
    prompt_two = f"Append marker {marker}-two to README first line"

    env = os.environ.copy()
    env.update(
        {
            "SUBMIT_PR_BODY": f"Automated test body {marker}",
        }
    )

    repo_arg = repo_url
    _run_cli_twice_and_assert_two_commits(
        repo_arg,
        slug,
        env,
        change_id,
        prompt_one,
        prompt_two,
    )
