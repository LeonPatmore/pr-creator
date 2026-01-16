from __future__ import annotations

import hashlib
import io
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from dulwich import porcelain
from dulwich.config import StackedConfig
from dulwich.repo import Repo
from github import Github
from github.GithubException import GithubException
from github.Repository import Repository

from pr_creator.git_urls import (
    github_slug_from_url,
    strip_auth_from_url,
    token_auth_github_url,
)
from pr_creator.github_client import get_github_client

from .base import SubmitChange

logger = logging.getLogger(__name__)


def _token_debug_str(token: str) -> str:
    """
    Return a safe token fingerprint for logs.

    We intentionally do NOT log any token characters. This is just a short SHA256
    fingerprint + length to help debug env propagation.
    """
    token = token or ""
    digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"len={len(token)} sha256[:10]={digest}"


def _load_repo(repo_path: Path) -> Repo:
    return Repo.discover(str(repo_path))


def _sha_to_hex(sha: bytes) -> str:
    """
    Dulwich SHA values can appear in a couple forms depending on version/context:
    - 20 raw bytes (binary SHA1)
    - 40 ASCII bytes of hex

    Always return the canonical 40-char hex string.
    """
    if not sha:
        return ""
    if len(sha) == 20:
        return sha.hex()
    if len(sha) == 40:
        try:
            s = sha.decode("ascii")
            if all(c in "0123456789abcdefABCDEF" for c in s):
                return s.lower()
        except Exception:
            pass
    return sha.hex()


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


def _remote_tracking_ref(branch: str) -> bytes:
    return f"refs/remotes/origin/{branch}".encode()


def _ahead_behind_vs_origin(repo: Repo, branch: str) -> tuple[int, int]:
    """
    Return (ahead, behind) commit counts for local HEAD vs origin/<branch>, using the
    locally-fetched remote tracking ref.

    If there is no origin tracking ref, treat it as (ahead=1, behind=0) so we attempt
    to push the local branch to origin.
    """
    local = repo.head()
    remote_ref = _remote_tracking_ref(branch)
    try:
        remote = repo.refs[remote_ref]
    except KeyError:
        remote = None
    if remote is None:
        return 1, 0

    ahead = sum(
        1
        for _ in repo.get_walker(
            include=[local],
            exclude=[remote],
        )
    )
    behind = sum(
        1
        for _ in repo.get_walker(
            include=[remote],
            exclude=[local],
        )
    )
    return ahead, behind


def _push_branch(
    repo: Repo, branch: str, token: str, origin_url: str, *, force: bool = False
) -> None:
    """Push branch to remote."""
    # Helpful for debugging env propagation without leaking the full token.
    logger.info("[submit] using GitHub token (%s)", _token_debug_str(token))
    push_url = token_auth_github_url(origin_url, token)
    if not push_url:
        raise RuntimeError(f"Unsupported origin URL for token push: {origin_url}")

    refspec = f"refs/heads/{branch}:refs/heads/{branch}"
    if force:
        refspec = f"+{refspec}"
    # Avoid logging tokens; log a sanitized URL and silence push output streams.
    logger.info(
        "[submit] %s %s to origin", "force-pushing" if force else "pushing", refspec
    )
    null_stream = io.BytesIO()
    porcelain.push(
        repo.path,
        push_url,
        refspecs=[refspec],
        errstream=null_stream,
    )


def _qualified_head(remote_repo: Repository, branch: str) -> str:
    # GitHub's API accepts both "branch" (same-repo) and "owner:branch". Using the qualified
    # form is more robust and matches our PR lookup logic.
    return f"{remote_repo.owner.login}:{branch}"


def _wait_for_remote_branch(
    remote_repo: Repository,
    branch: str,
    *,
    attempts: int = 6,
    initial_sleep_seconds: float = 0.5,
) -> None:
    """
    Ensure the pushed branch ref is visible to the GitHub API before creating a PR.

    We sometimes see eventual-consistency where the push succeeds but the subsequent PR creation
    returns 422 (invalid head) because the ref is not yet queryable.
    """
    sleep_s = initial_sleep_seconds
    last_exc: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            remote_repo.get_git_ref(f"heads/{branch}")
            return
        except GithubException as exc:
            last_exc = exc
            # 404 = ref not visible yet
            if exc.status != 404:
                raise
        time.sleep(sleep_s)
        sleep_s = min(sleep_s * 2, 5.0)
    raise RuntimeError(
        f"Remote branch not visible after push: {remote_repo.full_name} refs/heads/{branch}"
    ) from last_exc


def _build_pr_body(base_body: str, change_prompt: Optional[str]) -> str:
    """Build PR body with optional change prompt."""
    if change_prompt:
        return f"{base_body}\n\n## Change Prompt\n\n{change_prompt}"
    return base_body


def _get_remote_repo_and_base_branch(
    origin: str, gh: Github | None, base_branch: Optional[str]
) -> Tuple[Optional[Repository], str]:
    """Get remote repository and determine base branch."""
    if not gh:
        return None, base_branch or "main"

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


def _update_existing_pr(pr, pr_body: Optional[str] = None) -> None:
    """Update PR description if provided. Title is never updated for existing PRs."""
    if pr_body is None:
        return

    try:
        logger.info("[submit] updating PR description for %s", pr.html_url)
        pr.edit(body=pr_body)
    except GithubException as exc:
        logger.warning(
            "[submit] failed to update existing PR %s: %s",
            pr.html_url,
            exc,
        )


class GithubSubmitter(SubmitChange):
    def __init__(self, *, github_token: str | None = None) -> None:
        self.base_branch = os.environ.get("SUBMIT_PR_BASE") or None
        self.pr_body = os.environ.get(
            "SUBMIT_PR_BODY", "Automated changes generated by pr-creator."
        )
        self.github_token = github_token
        self._gh = get_github_client(github_token)

    def _ensure_branch(self, repo: Repo, branch: str | None) -> str:
        """Ensure we're on the correct branch and return its name."""
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
            return branch
        else:
            return _current_branch(repo)

    def _push_if_ahead(
        self,
        repo: Repo,
        current_branch: str,
        origin: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Push local commits if ahead of origin.

        Returns (pushed: bool, pushed_sha: Optional[str])
        """
        if not self.github_token:
            return False, None

        ahead, behind = _ahead_behind_vs_origin(repo, current_branch)
        if behind > 0 and ahead == 0:
            logger.warning(
                "[submit] local branch is behind origin/%s (behind=%s, ahead=%s); skipping push",
                current_branch,
                behind,
                ahead,
            )
            return False, None
        if ahead == 0:
            return False, None

        # If both ahead and behind, the change agent rewrote history (e.g., reset/amend).
        # Force push since we own this feature branch.
        force = behind > 0
        if force:
            logger.info(
                "[submit] local branch diverged from origin/%s (behind=%s, ahead=%s); force-pushing",
                current_branch,
                behind,
                ahead,
            )
        else:
            logger.info(
                "[submit] local branch ahead of origin/%s by %s commits; pushing",
                current_branch,
                ahead,
            )
        pushed_sha = _sha_to_hex(repo.head())
        _push_branch(repo, current_branch, self.github_token, origin, force=force)
        return True, pushed_sha

    def _handle_no_changes_to_push(
        self,
        remote_repo: Repository | None,
        current_branch: str,
        base_branch: str,
        origin: str,
        pr_body: str,
    ) -> Optional[Dict[str, str]]:
        """Handle case where there are no changes to push - check for existing PR."""
        logger.info("[submit] nothing to push")

        if not remote_repo:
            return None

        if current_branch == base_branch:
            return None

        existing_pr = _find_existing_pr(remote_repo, current_branch, base_branch)
        if existing_pr:
            # Return existing PR info so CI can run against latest commit
            _update_existing_pr(existing_pr, pr_body=pr_body)
            logger.info(
                "[submit] no changes pushed, but PR exists: %s", existing_pr.html_url
            )
            return {
                "repo_url": origin,
                "branch": current_branch,
                "pr_url": existing_pr.html_url,
                # Note: no pushed_sha since we didn't push anything
            }

        # No PR exists and nothing to push
        logger.info("[submit] no PR exists and nothing to push; skipping")
        return None

    def _find_or_create_pr(
        self,
        remote_repo: Repository | None,
        current_branch: str,
        base_branch: str,
        origin: str,
        pr_title: str,
        pr_body: str,
        pushed_sha: Optional[str],
    ) -> Optional[Dict[str, str]]:
        """Find existing PR or create a new one."""
        if not remote_repo:
            logger.warning("GitHub token not set; skipping PR creation")
            return {"repo_url": origin, "branch": current_branch, "pr_url": None}

        # Avoid creating PR when head matches base (no-op PR)
        if current_branch == base_branch:
            logger.warning(
                "Current branch '%s' matches base '%s'; skipping PR creation",
                current_branch,
                base_branch,
            )
            return {"repo_url": origin, "branch": current_branch, "pr_url": None}

        existing_pr = _find_existing_pr(remote_repo, current_branch, base_branch)
        if existing_pr:
            _update_existing_pr(existing_pr, pr_body=pr_body)
            result = {
                "repo_url": origin,
                "branch": current_branch,
                "pr_url": existing_pr.html_url,
            }
            if pushed_sha:
                result["pushed_sha"] = pushed_sha
            return result

        # Create new PR
        _wait_for_remote_branch(remote_repo, current_branch)
        head_ref = _qualified_head(remote_repo, current_branch)
        logger.info("[submit] creating PR head=%s base=%s", head_ref, base_branch)
        try:
            pr = remote_repo.create_pull(
                title=pr_title,
                body=pr_body,
                head=head_ref,
                base=base_branch,
            )
        except GithubException as exc:
            if exc.status == 422:
                existing_pr = _find_existing_pr(
                    remote_repo, current_branch, base_branch, include_closed=True
                )
                if existing_pr:
                    _update_existing_pr(existing_pr, pr_body=pr_body)
                    result = {
                        "repo_url": origin,
                        "branch": current_branch,
                        "pr_url": existing_pr.html_url,
                    }
                    if pushed_sha:
                        result["pushed_sha"] = pushed_sha
                    return result
            raise
        result = {"repo_url": origin, "branch": current_branch, "pr_url": pr.html_url}
        if pushed_sha:
            result["pushed_sha"] = pushed_sha
        return result

    def submit(
        self,
        repo_path: Path,
        change_prompt: str | None = None,
        change_id: str | None = None,
        branch: str | None = None,
        pr_title: str | None = None,
        commit_message: str | None = None,
    ) -> Optional[Dict[str, str]]:
        """
        Submit changes to GitHub by committing, pushing, and creating/updating PRs.

        Returns dict with repo_url, branch, pr_url, and optionally pushed_sha.
        Returns None if no changes and no existing PR.
        """
        repo = _load_repo(Path(repo_path))
        origin = strip_auth_from_url(_origin_url(repo))

        # Ensure we're on the correct branch
        current_branch = self._ensure_branch(repo, branch)
        logger.info("[submit] current branch=%s", current_branch)

        # Get remote repo and base branch
        remote_repo, base_branch = _get_remote_repo_and_base_branch(
            origin, self._gh, self.base_branch
        )

        pr_body = _build_pr_body(self.pr_body, change_prompt)
        pr_title_final = pr_title or "Automated changes"
        commit_message_final = commit_message or "Automated changes"

        # Check if there are local file changes
        if not _git_status_dirty(repo):
            return self._handle_clean_working_directory(
                repo, current_branch, origin, remote_repo, base_branch, pr_body
            )

        # Try to commit local changes
        committed = _commit_changes_if_needed(repo, commit_message_final)
        if not committed:
            return self._handle_no_commit_needed(
                repo, current_branch, origin, remote_repo, base_branch, pr_body
            )

        # We made a new commit - push and create/update PR
        return self._handle_new_commit(
            repo,
            current_branch,
            origin,
            remote_repo,
            base_branch,
            pr_title_final,
            pr_body,
        )

    def _handle_clean_working_directory(
        self,
        repo: Repo,
        current_branch: str,
        origin: str,
        remote_repo: Repository | None,
        base_branch: str,
        pr_body: str,
    ) -> Optional[Dict[str, str]]:
        """Handle case where working directory is clean (no uncommitted changes)."""
        logger.info("[submit] no local file changes detected")
        pushed, pushed_sha = self._push_if_ahead(repo, current_branch, origin)

        if not pushed:
            return self._handle_no_changes_to_push(
                remote_repo, current_branch, base_branch, origin, pr_body
            )

        # We pushed commits - find or create PR
        return self._find_or_create_pr(
            remote_repo,
            current_branch,
            base_branch,
            origin,
            "Automated changes",  # Title not provided in this path
            pr_body,
            pushed_sha,
        )

    def _handle_no_commit_needed(
        self,
        repo: Repo,
        current_branch: str,
        origin: str,
        remote_repo: Repository | None,
        base_branch: str,
        pr_body: str,
    ) -> Optional[Dict[str, str]]:
        """Handle case where staging found no changes vs HEAD."""
        logger.info("[submit] no staged changes vs HEAD; skipping commit/PR creation")

        # Check if there are already-committed changes to push
        pushed, pushed_sha = self._push_if_ahead(repo, current_branch, origin)
        if not pushed:
            return self._handle_no_changes_to_push(
                remote_repo, current_branch, base_branch, origin, pr_body
            )

        # We pushed existing commits - find or create PR
        return self._find_or_create_pr(
            remote_repo,
            current_branch,
            base_branch,
            origin,
            "Automated changes",  # Title not provided in this path
            pr_body,
            pushed_sha,
        )

    def _handle_new_commit(
        self,
        repo: Repo,
        current_branch: str,
        origin: str,
        remote_repo: Repository | None,
        base_branch: str,
        pr_title: str,
        pr_body: str,
    ) -> Optional[Dict[str, str]]:
        """Handle case where we just created a new commit."""
        if not self.github_token:
            logger.warning("GitHub token not set; skipping push/PR creation")
            return {"repo_url": origin, "branch": current_branch, "pr_url": None}

        # Push the new commit
        pushed_sha = _sha_to_hex(repo.head())
        ahead, behind = _ahead_behind_vs_origin(repo, current_branch)
        force = behind > 0
        if force:
            logger.info(
                "[submit] local branch diverged from origin/%s (behind=%s, ahead=%s); force-pushing new commit",
                current_branch,
                behind,
                ahead,
            )
        _push_branch(repo, current_branch, self.github_token, origin, force=force)

        # Find or create PR
        return self._find_or_create_pr(
            remote_repo,
            current_branch,
            base_branch,
            origin,
            pr_title,
            pr_body,
            pushed_sha,
        )
