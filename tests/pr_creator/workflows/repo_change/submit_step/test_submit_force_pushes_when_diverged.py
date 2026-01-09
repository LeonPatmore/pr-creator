from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_submit_force_pushes_when_branch_diverged_from_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    When a change agent resets or amends commits, the local branch diverges from origin
    (both ahead=1 and behind=1). This test verifies that we force-push in this scenario.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo, first_sha = _init_repo(repo_dir)

    # Create and checkout a feature branch.
    porcelain.branch_create(str(repo_dir), b"feature/test", first_sha)
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/feature/test")
    porcelain.checkout_branch(repo, "feature/test", force=True)

    # Create a commit and simulate it being pushed.
    (repo_dir / "README.md").write_text("hello world\n", encoding="utf-8")
    porcelain.add(str(repo_dir))
    porcelain.commit(
        str(repo_dir),
        message=b"second",
        author=b"tester <tester@example.com>",
        committer=b"tester <tester@example.com>",
        sign=False,
    )
    second_sha = repo.head()
    # Simulate the remote tracking ref pointing to the second commit.
    repo.refs[b"refs/remotes/origin/feature/test"] = second_sha

    # Now simulate the change agent resetting to first commit and creating a new commit.
    # This creates a diverged state: local is ahead by 1, behind by 1.
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/feature/test")
    repo.refs[b"refs/heads/feature/test"] = first_sha
    (repo_dir / "README.md").write_text("hello universe\n", encoding="utf-8")
    porcelain.add(str(repo_dir))
    porcelain.commit(
        str(repo_dir),
        message=b"third",
        author=b"tester <tester@example.com>",
        committer=b"tester <tester@example.com>",
        sign=False,
    )
    third_sha = repo.head()
    assert third_sha != second_sha  # different commit

    # Verify we're in a diverged state.
    ahead, behind = github_submitter._ahead_behind_vs_origin(repo, "feature/test")
    assert ahead == 1
    assert behind == 1

    dummy_remote_repo = SimpleNamespace()
    pushed_sha = github_submitter._sha_to_hex(third_sha)
    expected = {
        "repo_url": "https://github.com/example/acme.git",
        "branch": "feature/test",
        "pr_url": "https://github.com/example/acme/pull/123",
        "pushed_sha": pushed_sha,
    }

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

    push_calls: list[tuple[str, bool]] = []

    def _push(
        repo_obj: Repo, branch: str, token: str, origin_url: str, *, force: bool = False
    ) -> None:
        push_calls.append((branch, force))

    monkeypatch.setattr(github_submitter, "_push_branch", _push)

    mock_pr = SimpleNamespace(html_url="https://github.com/example/acme/pull/123")
    monkeypatch.setattr(
        github_submitter,
        "_find_existing_pr",
        lambda remote_repo, branch, base_branch, include_closed=False: mock_pr,
    )
    monkeypatch.setattr(
        github_submitter,
        "_update_existing_pr",
        lambda pr, pr_body=None, pr_title=None: None,
    )

    submitter = github_submitter.GithubSubmitter(github_token="dummy")
    result = submitter.submit(repo_dir, branch="feature/test")
    assert result == expected
    # Verify we force-pushed (force=True).
    assert push_calls == [("feature/test", True)]
