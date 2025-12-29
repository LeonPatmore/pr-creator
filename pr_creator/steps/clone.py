from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dulwich import porcelain
from dulwich.repo import Repo
from github import Auth, Github
from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.git_urls import github_slug_from_url, token_auth_github_url

logger = logging.getLogger(__name__)


def ensure_dir(path: Path) -> None:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)


def _get_branch_to_checkout(
    repo_url: str, change_id: Optional[str], branch_prefix: str, token: Optional[str]
) -> Optional[str]:
    """Check if a branch exists remotely for the given change_id and return it."""
    if not change_id or not token:
        return None

    try:
        slug = github_slug_from_url(repo_url)
        if not slug:
            return None

        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(slug)
        branch_name = f"{branch_prefix}-{change_id}"

        try:
            repo.get_branch(branch_name)
            logger.info(
                "Found existing branch %s for change_id %s", branch_name, change_id
            )
            return branch_name
        except Exception:
            logger.info(
                "Branch %s does not exist yet for change_id %s", branch_name, change_id
            )
            return None
    except Exception as e:
        logger.warning("Failed to check for existing branch: %s", e)
        return None


def _get_clone_url(repo_url: str) -> str:
    """Get authenticated clone URL if token is available."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        token_url = token_auth_github_url(repo_url, token)
        if token_url:
            return token_url
    return repo_url


def _get_target_path(repo_url: str, working_dir: Path) -> Path:
    """Get target path for cloning, ensuring uniqueness."""
    ensure_dir(working_dir)
    name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    return working_dir / f"{name}-{uuid.uuid4().hex[:8]}"


def _get_default_branch(repo_url: str, token: Optional[str]) -> str:
    """Get the default branch (main/master) for the repository."""
    try:
        slug = github_slug_from_url(repo_url)
        if slug and token:
            gh = Github(auth=Auth.Token(token))
            repo = gh.get_repo(slug)
            return repo.default_branch
    except Exception:
        pass
    return "main"  # Fallback to "main"


def clone_repo(
    repo_url: str, working_dir: Path, change_id: Optional[str] = None
) -> Path:
    """Clone a repository and checkout the appropriate branch."""
    target = _get_target_path(repo_url, working_dir)
    clone_url = _get_clone_url(repo_url)

    # Check if branch exists remotely
    branch_prefix = os.environ.get("SUBMIT_BRANCH_PREFIX", "auto/pr")
    token = os.environ.get("GITHUB_TOKEN")
    branch_to_checkout = _get_branch_to_checkout(
        repo_url, change_id, branch_prefix, token
    )

    if branch_to_checkout:
        # Branch exists on remote - clone normally first, then checkout the branch
        logger.info(
            "Cloning %s -> %s (checking out branch %s)",
            repo_url,
            target,
            branch_to_checkout,
        )
        # Clone with checkout=True to get a proper working directory with all files
        porcelain.clone(clone_url, target, checkout=True)
        repo = Repo.discover(str(target))

        # Fetch the branch
        porcelain.fetch(repo.path, clone_url)

        # Create local branch tracking remote if it doesn't exist
        remote_ref = f"refs/remotes/origin/{branch_to_checkout}".encode()
        if remote_ref in repo.refs:
            branch_ref = f"refs/heads/{branch_to_checkout}".encode()
            if branch_ref not in repo.refs:
                porcelain.branch_create(
                    repo.path, branch_to_checkout.encode(), repo.refs[remote_ref]
                )

            # Checkout the branch - this should write all files including .github
            porcelain.checkout_branch(repo, branch_to_checkout, force=True)
            logger.info("Checked out branch %s", branch_to_checkout)
        else:
            # Fallback to default branch if fetch didn't work
            default_branch = _get_default_branch(repo_url, token)
            logger.warning(
                "Remote branch %s not found, falling back to %s",
                branch_to_checkout,
                default_branch,
            )
            default_branch_ref = f"refs/heads/{default_branch}".encode()
            if default_branch_ref in repo.refs:
                repo.refs.set_symbolic_ref(b"HEAD", default_branch_ref)
                porcelain.reset(repo.path, "hard", repo.refs[default_branch_ref])
                porcelain.checkout_branch(repo, default_branch, force=True)
            else:
                # If default branch ref doesn't exist, use HEAD
                porcelain.reset(repo.path, "hard", b"HEAD")
                porcelain.checkout_branch(repo, "HEAD", force=True)
    else:
        # Branch does not exist - checkout main branch
        default_branch = _get_default_branch(repo_url, token)
        logger.info(
            "Cloning %s -> %s (checking out %s)", repo_url, target, default_branch
        )
        porcelain.clone(clone_url, target, checkout=True)

        # Create and checkout a new feature branch so submitter only submits
        repo = Repo.discover(str(target))
        head_ref = repo.refs.read_ref(b"HEAD")
        base_ref = (
            head_ref
            if head_ref in repo.refs
            else f"refs/heads/{default_branch}".encode()
        )
        new_branch = (
            f"{branch_prefix}-{change_id}"
            if change_id
            else f"{branch_prefix}-{uuid.uuid4().hex[:8]}"
        )
        logger.info("Creating feature branch %s from %s", new_branch, base_ref.decode())
        porcelain.branch_create(repo.path, new_branch.encode(), repo.refs[base_ref])
        branch_ref = f"refs/heads/{new_branch}".encode()
        repo.refs.set_symbolic_ref(b"HEAD", branch_ref)
        porcelain.reset(repo.path, "hard", branch_ref)
        porcelain.checkout_branch(repo, new_branch, force=True)
        # Ensure HEAD persists on the new branch
        repo.refs.set_symbolic_ref(b"HEAD", branch_ref)

    return target


def _branch_exists_remotely(repo_url: str, change_id: Optional[str]) -> bool:
    """Check if a branch exists remotely for the given change_id."""
    branch_prefix = os.environ.get("SUBMIT_BRANCH_PREFIX", "auto/pr")
    token = os.environ.get("GITHUB_TOKEN")
    return (
        _get_branch_to_checkout(repo_url, change_id, branch_prefix, token) is not None
    )


@dataclass
class CloneRepo(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        """Clone repository and determine next step based on branch existence."""
        path = clone_repo(self.repo_url, ctx.state.working_dir, ctx.state.change_id)
        ctx.state.cloned[self.repo_url] = path

        if _branch_exists_remotely(self.repo_url, ctx.state.change_id):
            logger.info(
                "Branch exists remotely for %s, skipping relevance check (will re-apply changes)",
                self.repo_url,
            )
            ctx.state.relevant.append(self.repo_url)
            from .apply import ApplyChanges

            return ApplyChanges(repo_url=self.repo_url)

        from .evaluate import EvaluateRelevance

        return EvaluateRelevance(repo_url=self.repo_url)
