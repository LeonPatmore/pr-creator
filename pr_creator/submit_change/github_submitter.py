from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from dulwich import porcelain
from dulwich.config import StackedConfig
from dulwich.repo import Repo
from github import Auth, Github
from github.GithubException import GithubException
from github.Repository import Repository

from .base import SubmitChange
from pr_creator.git_urls import (
    github_slug_from_url,
    strip_auth_from_url,
    token_auth_github_url,
)

logger = logging.getLogger(__name__)


def _load_repo(repo_path: Path) -> Repo:
    return Repo.discover(str(repo_path))


def _origin_url(repo: Repo) -> str:
    cfg: StackedConfig = repo.get_config()
    url_bytes = cfg.get((b"remote", b"origin"), b"url")
    return url_bytes.decode()


def _current_branch(repo: Repo) -> str:
    """Get the current branch (assumes HEAD points to the desired branch)."""
    head = repo.refs.read_ref(b"HEAD")
    if head and head.startswith(b"refs/heads/"):
        return head[len(b"refs/heads/") :].decode()
    # Fallback: pick a branch whose ref matches HEAD target, or any branch
    head_sha = repo.refs.read_ref(b"HEAD")
    for ref_name in repo.refs.keys():
        if ref_name.startswith(b"refs/heads/") and repo.refs[ref_name] == head_sha:
            return ref_name[len(b"refs/heads/") :].decode()
    for ref_name in repo.refs.keys():
        if ref_name.startswith(b"refs/heads/"):
            return ref_name[len(b"refs/heads/") :].decode()
    raise RuntimeError("HEAD is not pointing to a branch; clone step should set it")


def _config_value(
    cfg: StackedConfig, section: tuple[bytes, ...], name: bytes
) -> Optional[str]:
    try:
        value = cfg.get(section, name)
    except KeyError:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _ensure_identity(repo: Repo) -> tuple[str, str]:
    cfg = repo.get_config()
    name = os.environ.get("GIT_AUTHOR_NAME") or _config_value(cfg, (b"user",), b"name")
    email = os.environ.get("GIT_AUTHOR_EMAIL") or _config_value(
        cfg, (b"user",), b"email"
    )
    author = f"{name or 'pr-creator'} <{email or 'pr-creator@example.com'}>"
    return author, author


def _git_status_dirty(repo: Repo) -> bool:
    status = porcelain.status(repo)
    return bool(status.staged or status.unstaged or status.untracked)


def _index_has_changes_vs_head(repo: Repo) -> bool:
    """Return True if the index differs from HEAD (i.e., there is something to commit)."""
    head_commit = repo[repo.head()]
    head_tree = head_commit.tree
    index = repo.open_index()
    return any(index.changes_from_tree(repo.object_store, head_tree))


def _commit_changes_if_needed(repo: Repo, message: str) -> bool:
    author, committer = _ensure_identity(repo)
    porcelain.add(repo.path)

    # Be strict: only commit when the staged/index state actually differs from HEAD.
    # This avoids empty/no-op commits in cases where `status()` can be misleading.
    if not _index_has_changes_vs_head(repo):
        return False

    porcelain.commit(
        repo.path,
        message=message,
        author=author.encode(),
        committer=committer.encode(),
        sign=False,
    )
    return True


def _push_branch(repo: Repo, branch: str, token: str, origin_url: str) -> None:
    """Push branch to remote."""
    push_url = token_auth_github_url(origin_url, token)
    if not push_url:
        raise RuntimeError(f"Unsupported origin URL for token push: {origin_url}")

    refspec = f"refs/heads/{branch}:refs/heads/{branch}"
    # Avoid logging tokens; log a sanitized URL and silence push output streams.
    logger.info("[submit] pushing %s to origin", refspec)
    null_stream = io.BytesIO()
    porcelain.push(
        repo.path,
        push_url,
        refspecs=[refspec],
        errstream=null_stream,
        outstream=null_stream,
    )


def _build_pr_body(base_body: str, change_prompt: Optional[str]) -> str:
    """Build PR body with optional change prompt."""
    if change_prompt:
        return f"{base_body}\n\n## Change Prompt\n\n{change_prompt}"
    return base_body


def _get_remote_repo_and_base_branch(
    origin: str, github_token: Optional[str], base_branch: Optional[str]
) -> Tuple[Optional[Repository], str]:
    """Get remote repository and determine base branch."""
    if not github_token:
        return None, base_branch or "main"

    gh = Github(auth=Auth.Token(github_token))
    slug = github_slug_from_url(origin)
    if not slug:
        return None, base_branch or "main"

    remote_repo = gh.get_repo(slug)
    if base_branch is None:
        base_branch = remote_repo.default_branch

    return remote_repo, base_branch or "main"


def _find_existing_pr(
    remote_repo: Repository, branch: str, base_branch: str, include_closed: bool = False
):
    """Return an existing PR for the given branch/base combination if present."""
    head = f"{remote_repo.owner.login}:{branch}"
    states = ["open", "closed"] if include_closed else ["open"]

    for state in states:
        try:
            pulls = remote_repo.get_pulls(state=state, head=head, base=base_branch)
            for pr in pulls:
                return pr
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "[submit] failed to list %s PRs for head=%s base=%s: %s",
                state,
                head,
                base_branch,
                exc,
            )
            return None
    return None


def _return_existing_pr_if_any(
    remote_repo: Repository,
    origin: str,
    branch: str,
    base_branch: str,
    include_closed: bool = False,
) -> Optional[Dict[str, str]]:
    existing_pr = _find_existing_pr(
        remote_repo, branch, base_branch, include_closed=include_closed
    )
    if not existing_pr:
        return None
    logger.info(
        "[submit] found existing PR for branch %s -> %s",
        branch,
        existing_pr.html_url,
    )
    return {
        "repo_url": origin,
        "branch": branch,
        "pr_url": existing_pr.html_url,
    }


class GithubSubmitter(SubmitChange):
    def __init__(self) -> None:
        self.base_branch = os.environ.get("SUBMIT_PR_BASE") or None
        self.pr_body = os.environ.get(
            "SUBMIT_PR_BODY", "Automated changes generated by pr-creator."
        )
        self.github_token = os.environ.get("GITHUB_TOKEN")

    def submit(
        self,
        repo_path: Path,
        change_prompt: str | None = None,
        change_id: str | None = None,
        branch: str | None = None,
        pr_title: str | None = None,
        commit_message: str | None = None,
    ) -> Optional[Dict[str, str]]:
        repo = _load_repo(Path(repo_path))
        origin = strip_auth_from_url(_origin_url(repo))

        # Ensure we are on the intended branch (change agents may checkout base)
        if branch:
            desired_ref = f"refs/heads/{branch}".encode()
            if desired_ref in repo.refs:
                repo.refs.set_symbolic_ref(b"HEAD", desired_ref)
                porcelain.checkout_branch(repo, branch, force=True)
            else:
                # Create the branch from current HEAD if it is missing
                head_target = repo.refs.read_ref(b"HEAD")
                logger.warning(
                    "[submit] requested branch %s not found locally; creating from HEAD %s",
                    branch,
                    head_target,
                )
                porcelain.branch_create(repo.path, branch.encode(), head_target)
                repo.refs.set_symbolic_ref(b"HEAD", desired_ref)
                porcelain.checkout_branch(repo, branch, force=True)
            current_branch = branch
        else:
            current_branch = _current_branch(repo)

        logger.info("[submit] current branch=%s", current_branch)

        # Get remote repo and base branch
        remote_repo, base_branch = _get_remote_repo_and_base_branch(
            origin, self.github_token, self.base_branch
        )

        pr_body = _build_pr_body(self.pr_body, change_prompt)
        pr_title_final = pr_title or "Automated changes"
        commit_message_final = commit_message or "Automated changes"

        # Commit only when there is something to commit.
        # Note: `status()` is a cheap pre-check, but we still double-check after staging.
        if not _git_status_dirty(repo):
            logger.info("[submit] no changes to commit; skipping PR creation")
            return None

        committed = _commit_changes_if_needed(repo, commit_message_final)
        if not committed:
            logger.info(
                "[submit] no staged changes vs HEAD; skipping commit/PR creation"
            )
            return None

        if not self.github_token:
            logger.warning("GITHUB_TOKEN not set; skipping push/PR creation")
            return {"repo_url": origin, "branch": branch, "pr_url": None}

        _push_branch(repo, branch, self.github_token, origin)

        if not remote_repo:
            logger.warning("GITHUB_TOKEN not set; skipping PR creation")
            return {"repo_url": origin, "branch": branch, "pr_url": None}

        # Avoid creating PR when head matches base (no-op PR)
        if branch == base_branch:
            logger.warning(
                "Current branch '%s' matches base '%s'; skipping PR creation",
                branch,
                base_branch,
            )
            return {"repo_url": origin, "branch": branch, "pr_url": None}

        existing = _return_existing_pr_if_any(remote_repo, origin, branch, base_branch)
        if existing:
            return existing

        # Create new PR
        logger.info("[submit] creating PR head=%s base=%s", branch, base_branch)
        try:
            pr = remote_repo.create_pull(
                title=pr_title_final,
                body=pr_body,
                head=branch,
                base=base_branch,
            )
        except GithubException as exc:
            if exc.status == 422:
                existing = _return_existing_pr_if_any(
                    remote_repo,
                    origin,
                    branch,
                    base_branch,
                    include_closed=True,
                )
                if existing:
                    return existing
            raise
        return {"repo_url": origin, "branch": branch, "pr_url": pr.html_url}
