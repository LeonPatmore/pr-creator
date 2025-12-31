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


@dataclass(frozen=True)
class CloneResult:
    path: Path
    branch: str


def ensure_dir(path: Path) -> None:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)


def _find_branch_with_change_prefix(
    repo_url: str,
    token: Optional[str],
    change_id: Optional[str],
    preferred: Optional[str],
) -> Optional[str]:
    """Return a remote branch that starts with the change_id prefix, if any."""
    if not change_id or not token:
        return None

    try:
        slug = github_slug_from_url(repo_url)
        if not slug:
            return None

        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(slug)
        prefix = f"{change_id}/"
        first_match: Optional[str] = None

        for branch in repo.get_branches():
            name = branch.name
            if not name.startswith(prefix):
                continue
            if preferred and name == preferred:
                logger.info(
                    "Found branch %s matching change id prefix %s", name, prefix
                )
                return name
            if first_match is None:
                first_match = name

        if first_match:
            logger.info(
                "Found branch %s matching change id prefix %s", first_match, prefix
            )
        return first_match
    except Exception as exc:
        logger.info(
            "Could not search for branches with change id prefix %s: %s", change_id, exc
        )
        return None


def _get_branch_to_checkout(
    repo_url: str,
    token: Optional[str],
    branch_name: Optional[str],
    change_id: Optional[str],
) -> Optional[str]:
    """
    Determine an existing remote branch to reuse.

    Priority:
    1) Any branch matching the change_id prefix (preferred if it matches branch_name).
    2) Exact branch_name match.
    """
    # First, try to reuse any branch that shares the change_id prefix.
    branch_from_prefix = _find_branch_with_change_prefix(
        repo_url, token, change_id, branch_name
    )
    if branch_from_prefix:
        return branch_from_prefix

    if not branch_name or not token:
        return None
    try:
        slug = github_slug_from_url(repo_url)
        if not slug:
            return None
        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(slug)
        repo.get_branch(branch_name)
        logger.info("Found existing branch %s", branch_name)
        return branch_name
    except Exception:
        logger.info("Branch %s does not exist yet", branch_name)
        return None


def _get_clone_url(repo_url: str) -> str:
    """Get authenticated clone URL if token is available."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        token_url = token_auth_github_url(repo_url, token)
        if token_url:
            return token_url
    return repo_url


def _sanitize_change_id(change_id: str) -> str:
    """Make change_id safe for directory names."""
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in change_id)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-_") or "change"


def _get_target_path(
    repo_url: str, working_dir: Path, change_id: Optional[str]
) -> Path:
    """Get target path for cloning; deterministic when change_id is provided."""
    ensure_dir(working_dir)
    name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    if change_id:
        safe_id = _sanitize_change_id(change_id)
        return working_dir / f"{name}-{safe_id}"
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
    repo_url: str,
    working_dir: Path,
    change_id: Optional[str] = None,
    branch_name: Optional[str] = None,
) -> CloneResult:
    """Clone a repository and checkout the appropriate branch."""
    if not branch_name:
        raise RuntimeError("Branch name must be provided by naming step before clone.")
    target = _get_target_path(repo_url, working_dir, change_id)
    clone_url = _get_clone_url(repo_url)

    # Check if branch exists remotely
    token = os.environ.get("GITHUB_TOKEN")
    branch_to_checkout = _get_branch_to_checkout(
        repo_url, token, branch_name, change_id
    )

    if not target.exists():
        logger.info("No existing workspace at %s; will clone", target)
    repo_exists = target.exists() and (target / ".git").exists()
    if target.exists() and not repo_exists:
        logger.info(
            "Not reusing existing path %s because .git is missing (likely not a repo)",
            target,
        )

    def _load_or_clone_repo() -> Repo:
        """Load existing repo if available, otherwise clone a fresh copy."""
        if repo_exists:
            logger.info("Reusing existing workspace at %s", target)
            try:
                return Repo.discover(str(target))
            except Exception as exc:
                logger.warning(
                    "Existing workspace at %s is invalid; recloning: %s", target, exc
                )
                # Provide extra context for reuse failure.
                logger.info(
                    "Recloning because workspace reuse failed (discover): %s", exc
                )
        logger.info("Cloning %s -> %s", repo_url, target)
        porcelain.clone(clone_url, target, checkout=True)
        return Repo.discover(str(target))

    repo = _load_or_clone_repo()

    if branch_to_checkout:
        # Ensure we have up-to-date refs before checking out.
        try:
            porcelain.fetch(repo.path, clone_url)
        except Exception as exc:
            logger.warning("Fetch failed for %s: %s", repo_url, exc)

        branch_ref = f"refs/heads/{branch_to_checkout}".encode()
        # Create local branch tracking remote if it doesn't exist
        remote_ref = f"refs/remotes/origin/{branch_to_checkout}".encode()
        if branch_ref in repo.refs:
            porcelain.checkout_branch(repo, branch_to_checkout, force=True)
            logger.info("Checked out existing local branch %s", branch_to_checkout)
        elif remote_ref in repo.refs:
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
        # Branch does not exist - checkout main branch and create new feature branch
        default_branch = _get_default_branch(repo_url, token)
        if not repo_exists:
            logger.info(
                "Checking out %s for new branch %s in fresh clone",
                default_branch,
                branch_name,
            )
        else:
            logger.info(
                "Reusing existing workspace for new branch %s (default base %s)",
                branch_name,
                default_branch,
            )

        try:
            porcelain.fetch(repo.path, clone_url)
        except Exception:
            # Non-fatal: proceed with existing refs
            pass

        head_ref = repo.refs.read_ref(b"HEAD")
        base_ref = (
            head_ref
            if head_ref in repo.refs
            else f"refs/heads/{default_branch}".encode()
        )
        new_branch = branch_name
        branch_ref = f"refs/heads/{new_branch}".encode()
        if branch_ref not in repo.refs:
            logger.info(
                "Creating feature branch %s from %s", new_branch, base_ref.decode()
            )
            porcelain.branch_create(repo.path, new_branch.encode(), repo.refs[base_ref])
        else:
            logger.info("Reusing existing local branch %s", new_branch)
        repo.refs.set_symbolic_ref(b"HEAD", branch_ref)
        porcelain.reset(repo.path, "hard", branch_ref)
        porcelain.checkout_branch(repo, new_branch, force=True)
        # Ensure HEAD persists on the new branch
        repo.refs.set_symbolic_ref(b"HEAD", branch_ref)

    # Do not rely on HEAD being a symbolic ref here: some porcelain operations can leave
    # HEAD detached/non-symbolic even though the intended branch is known.
    if branch_to_checkout:
        return CloneResult(path=target, branch=branch_to_checkout)
    return CloneResult(path=target, branch=new_branch)


def _branch_exists_remotely(
    repo_url: str, change_id: Optional[str], branch_name: Optional[str]
) -> bool:
    """Check if a branch exists remotely for the given explicit name."""
    token = os.environ.get("GITHUB_TOKEN")
    return _get_branch_to_checkout(repo_url, token, branch_name, change_id) is not None


@dataclass
class CloneRepo(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        """Clone repository and determine next step based on branch existence."""
        branch_name = ctx.state.branches.get(self.repo_url)
        result = clone_repo(
            self.repo_url, ctx.state.working_dir, ctx.state.change_id, branch_name
        )
        ctx.state.cloned[self.repo_url] = result.path
        ctx.state.branches[self.repo_url] = result.branch

        if _branch_exists_remotely(self.repo_url, ctx.state.change_id, branch_name):
            logger.info(
                "Branch exists remotely for %s, skipping relevance check (will re-apply changes)",
                self.repo_url,
            )
            ctx.state.relevant.append(self.repo_url)
            from .apply import ApplyChanges

            return ApplyChanges(repo_url=self.repo_url)

        from .evaluate import EvaluateRelevance

        return EvaluateRelevance(repo_url=self.repo_url)
