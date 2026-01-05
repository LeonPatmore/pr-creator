from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_submit_creates_pr_with_qualified_head(tmp_path: Path, monkeypatch) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo, first_sha = _init_repo(repo_dir)

    porcelain.branch_create(str(repo_dir), b"feature/test", first_sha)
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/feature/test")
    porcelain.checkout_branch(repo, "feature/test", force=True)

    # Local is ahead of origin tracking
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

    create_calls: list[dict] = []

    class DummyRepo:
        owner = SimpleNamespace(login="acme")
        full_name = "acme/widgets"

        def get_git_ref(self, ref: str):
            assert ref == "heads/feature/test"
            return True

        def create_pull(self, *, title: str, body: str, head: str, base: str):
            create_calls.append(
                {"title": title, "body": body, "head": head, "base": base}
            )
            return SimpleNamespace(html_url="https://github.com/x/y/pull/1")

        def get_pulls(self, **kwargs):
            # No existing PRs
            return []

    dummy_remote_repo = DummyRepo()

    monkeypatch.setattr(
        github_submitter,
        "_origin_url",
        lambda _repo: "https://github.com/acme/widgets.git",
    )
    monkeypatch.setattr(
        github_submitter,
        "_get_remote_repo_and_base_branch",
        lambda origin, github_token, base_branch: (dummy_remote_repo, "main"),
    )
    monkeypatch.setattr(github_submitter, "_push_branch", lambda *args, **kwargs: None)

    submitter = github_submitter.GithubSubmitter(github_token="dummy")
    result = submitter.submit(repo_dir, branch="feature/test")

    assert result and result["pr_url"] == "https://github.com/x/y/pull/1"
    assert create_calls, "Expected create_pull to be called"
    assert create_calls[0]["head"] == "acme:feature/test"


def test_wait_for_remote_branch_retries_on_404(monkeypatch) -> None:
    class DummyRepo:
        owner = SimpleNamespace(login="acme")
        full_name = "acme/widgets"

        def __init__(self) -> None:
            self.calls = 0

        def get_git_ref(self, ref: str):
            self.calls += 1
            if self.calls < 3:
                raise github_submitter.GithubException(
                    404, {"message": "Not Found"}, {}
                )
            return True

    dummy = DummyRepo()
    monkeypatch.setattr(github_submitter.time, "sleep", lambda *_args, **_kwargs: None)
    github_submitter._wait_for_remote_branch(dummy, "feature/test", attempts=5)
    assert dummy.calls == 3
