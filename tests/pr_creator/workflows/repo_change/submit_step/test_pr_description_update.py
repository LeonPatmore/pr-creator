from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from dulwich import porcelain
from dulwich.repo import Repo

import pr_creator.workflows.repo_change.submit_step.github_submitter as github_submitter


def _init_repo(repo_dir: Path) -> tuple[Repo, bytes]:
    porcelain.init(str(repo_dir))
    (repo_dir / "README.md").write_text("hello\n", encoding="utf-8")
    porcelain.add(str(repo_dir))
    porcelain.commit(
        str(repo_dir),
        message=b"init",
        author=b"tester <tester@example.com>",
        committer=b"tester <tester@example.com>",
        sign=False,
    )
    repo = Repo.discover(str(repo_dir))
    return repo, repo.head()


def test_submit_updates_pr_description_when_pr_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    When a PR already exists for the branch, the PR description should be updated
    with the current prompt (as it may have changed from the first run).
    The PR title should NOT be updated.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo, first_sha = _init_repo(repo_dir)

    # Create and checkout a feature branch.
    porcelain.branch_create(str(repo_dir), b"feature/test", first_sha)
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/feature/test")
    porcelain.checkout_branch(repo, "feature/test", force=True)

    # Simulate the fetched remote tracking branch pointing to the old commit.
    repo.refs[b"refs/remotes/origin/feature/test"] = first_sha

    # Create a new commit locally.
    (repo_dir / "README.md").write_text("hello world\n", encoding="utf-8")
    porcelain.add(str(repo_dir))
    porcelain.commit(
        str(repo_dir),
        message=b"second",
        author=b"tester <tester@example.com>",
        committer=b"tester <tester@example.com>",
        sign=False,
    )

    # Mock existing PR with edit method
    mock_pr = Mock()
    mock_pr.html_url = "https://github.com/example/acme/pull/123"
    mock_pr.edit = Mock()

    dummy_remote_repo = SimpleNamespace(
        owner=SimpleNamespace(login="example"),
        default_branch="main",
    )

    monkeypatch.setattr(
        github_submitter,
        "_origin_url",
        lambda _repo: "https://github.com/example/acme.git",
    )
    monkeypatch.setattr(
        github_submitter,
        "_get_remote_repo_and_base_branch",
        lambda origin, github_token, base_branch: (dummy_remote_repo, "main"),
    )
    monkeypatch.setattr(
        github_submitter,
        "_push_branch",
        lambda repo_obj, branch, token, origin_url, *, force=False: None,
    )
    monkeypatch.setattr(
        github_submitter,
        "_find_existing_pr",
        lambda remote_repo, branch, base_branch, include_closed=False: mock_pr,
    )

    # Submit with a change prompt
    submitter = github_submitter.GithubSubmitter(github_token="dummy")
    result = submitter.submit(
        repo_dir,
        branch="feature/test",
        change_prompt="Updated prompt describing the changes",
        pr_title="Updated PR Title",
    )

    # Verify the PR was returned
    assert result is not None
    assert result["pr_url"] == "https://github.com/example/acme/pull/123"

    # Verify PR description was updated with the new prompt, but title was NOT updated
    mock_pr.edit.assert_called_once()
    call_kwargs = mock_pr.edit.call_args.kwargs
    assert "body" in call_kwargs
    assert "Updated prompt describing the changes" in call_kwargs["body"]
    assert "title" not in call_kwargs


def test_submit_updates_pr_description_only_when_pr_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verify that PR description is updated when pr_body is provided, but title is never updated.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo, first_sha = _init_repo(repo_dir)

    porcelain.branch_create(str(repo_dir), b"feature/test", first_sha)
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/feature/test")
    porcelain.checkout_branch(repo, "feature/test", force=True)
    repo.refs[b"refs/remotes/origin/feature/test"] = first_sha

    (repo_dir / "README.md").write_text("hello world\n", encoding="utf-8")
    porcelain.add(str(repo_dir))
    porcelain.commit(
        str(repo_dir),
        message=b"second",
        author=b"tester <tester@example.com>",
        committer=b"tester <tester@example.com>",
        sign=False,
    )

    mock_pr = Mock()
    mock_pr.html_url = "https://github.com/example/acme/pull/456"
    mock_pr.edit = Mock()

    dummy_remote_repo = SimpleNamespace(
        owner=SimpleNamespace(login="example"),
        default_branch="main",
    )

    monkeypatch.setattr(
        github_submitter,
        "_origin_url",
        lambda _repo: "https://github.com/example/acme.git",
    )
    monkeypatch.setattr(
        github_submitter,
        "_get_remote_repo_and_base_branch",
        lambda origin, github_token, base_branch: (dummy_remote_repo, "main"),
    )
    monkeypatch.setattr(
        github_submitter,
        "_push_branch",
        lambda repo_obj, branch, token, origin_url, *, force=False: None,
    )
    monkeypatch.setattr(
        github_submitter,
        "_find_existing_pr",
        lambda remote_repo, branch, base_branch, include_closed=False: mock_pr,
    )

    # Submit with just a change prompt (no explicit pr_title)
    submitter = github_submitter.GithubSubmitter(github_token="dummy")
    result = submitter.submit(
        repo_dir,
        branch="feature/test",
        change_prompt="Another updated prompt",
    )

    assert result is not None
    assert result["pr_url"] == "https://github.com/example/acme/pull/456"

    # Verify PR description was updated but title was NOT
    mock_pr.edit.assert_called_once()
    call_kwargs = mock_pr.edit.call_args.kwargs
    assert "body" in call_kwargs
    assert "Another updated prompt" in call_kwargs["body"]
    assert "title" not in call_kwargs
