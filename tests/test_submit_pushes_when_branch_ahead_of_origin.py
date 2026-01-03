from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from dulwich import porcelain
from dulwich.repo import Repo

import pr_creator.submit_change.github_submitter as github_submitter


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


def test_submit_pushes_when_clean_but_branch_ahead_of_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo, first_sha = _init_repo(repo_dir)

    # Create and checkout a feature branch.
    porcelain.branch_create(str(repo_dir), b"feature/test", first_sha)
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/feature/test")
    porcelain.checkout_branch(repo, "feature/test", force=True)

    # Simulate the fetched remote tracking branch pointing to the old commit.
    repo.refs[b"refs/remotes/origin/feature/test"] = first_sha

    # Create a new commit locally (working tree ends up clean).
    (repo_dir / "README.md").write_text("hello world\n", encoding="utf-8")
    porcelain.add(str(repo_dir))
    porcelain.commit(
        str(repo_dir),
        message=b"second",
        author=b"tester <tester@example.com>",
        committer=b"tester <tester@example.com>",
        sign=False,
    )
    assert repo.head() != first_sha  # local HEAD is ahead of origin tracking

    monkeypatch.setenv("GITHUB_TOKEN", "dummy")

    dummy_remote_repo = SimpleNamespace()
    expected = {
        "repo_url": "https://github.com/example/acme.git",
        "branch": "feature/test",
        "pr_url": "https://github.com/example/acme/pull/123",
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

    push_calls: list[str] = []

    def _push(repo_obj: Repo, branch: str, token: str, origin_url: str) -> None:
        push_calls.append(branch)

    monkeypatch.setattr(github_submitter, "_push_branch", _push)
    monkeypatch.setattr(
        github_submitter,
        "_return_existing_pr_if_any",
        lambda remote_repo, origin, branch, base_branch, include_closed=False: expected,
    )

    submitter = github_submitter.GithubSubmitter()
    result = submitter.submit(repo_dir, branch="feature/test")
    assert result == expected
    assert push_calls == ["feature/test"]
