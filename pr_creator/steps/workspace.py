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
    path.mkdir(parents=True, exist_ok=True)


def _find_branch_with_change_prefix(
    repo_url: str,
    token: Optional[str],
    change_id: Optional[str],
    preferred: Optional[str],
) -> Optional[str]:
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
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        token_url = token_auth_github_url(repo_url, token)
        if token_url:
            return token_url
    return repo_url


def _sanitize_change_id(change_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in change_id)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-_") or "change"


def _get_target_path(
    repo_url: str, working_dir: Path, change_id: Optional[str]
) -> Path:
    ensure_dir(working_dir)
    name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    if change_id:
        safe_id = _sanitize_change_id(change_id)
        return working_dir / f"{name}-{safe_id}"
    return working_dir / f"{name}-{uuid.uuid4().hex[:8]}"


def _get_default_branch(repo_url: str, token: Optional[str]) -> str:
    try:
        slug = github_slug_from_url(repo_url)
        if slug and token:
            gh = Github(auth=Auth.Token(token))
            repo = gh.get_repo(slug)
            return repo.default_branch
    except Exception:
        pass
    return "main"


def load_or_clone_repo(target: Path, repo_url: str, clone_url: str) -> Repo:
    if target.exists() and (target / ".git").exists():
        logger.info("Reusing existing workspace at %s", target)
        try:
            return Repo.discover(str(target))
        except Exception as exc:
            logger.warning(
                "Existing workspace at %s is invalid; recloning: %s", target, exc
            )
    else:
        if target.exists():
            logger.info(
                "Not reusing existing path %s because .git is missing (likely not a repo)",
                target,
            )
        else:
            logger.info("No existing workspace at %s; will clone", target)
    logger.info("Cloning %s -> %s", repo_url, target)
    porcelain.clone(clone_url, target, checkout=True)
    return Repo.discover(str(target))


def fetch_refs(repo: Repo, clone_url: str, repo_url: str) -> None:
    try:
        porcelain.fetch(repo.path, clone_url)
    except Exception as exc:
        logger.warning("Fetch failed for %s: %s", repo_url, exc)


def ensure_branch_from_remote(
    repo: Repo, branch: str, repo_url: str, token: Optional[str]
) -> None:
    branch_ref = f"refs/heads/{branch}".encode()
    remote_ref = f"refs/remotes/origin/{branch}".encode()
    if remote_ref not in repo.refs:
        default_branch = _get_default_branch(repo_url, token)
        logger.warning(
            "Remote branch %s not found, falling back to %s", branch, default_branch
        )
        base_ref = f"refs/heads/{default_branch}".encode()
        if base_ref in repo.refs:
            repo.refs.set_symbolic_ref(b"HEAD", base_ref)
            porcelain.reset(repo.path, "hard", repo.refs[base_ref])
            porcelain.checkout_branch(repo, default_branch, force=True)
        else:
            porcelain.reset(repo.path, "hard", b"HEAD")
            porcelain.checkout_branch(repo, "HEAD", force=True)
        return

    if branch_ref in repo.refs:
        porcelain.reset(repo.path, "hard", repo.refs[remote_ref])
        logger.info("Updated local branch %s to remote before checkout", branch)
    else:
        porcelain.branch_create(repo.path, branch.encode(), repo.refs[remote_ref])
        logger.info("Created local branch %s from remote", branch)
    porcelain.checkout_branch(repo, branch, force=True)
    logger.info("Checked out branch %s", branch)


def create_branch_from_default(
    repo: Repo, new_branch: str, repo_url: str, token: Optional[str]
) -> None:
    default_branch = _get_default_branch(repo_url, token)
    head_ref = repo.refs.read_ref(b"HEAD")
    base_ref = (
        head_ref if head_ref in repo.refs else f"refs/heads/{default_branch}".encode()
    )
    branch_ref = f"refs/heads/{new_branch}".encode()
    if branch_ref not in repo.refs:
        logger.info("Creating feature branch %s from %s", new_branch, base_ref.decode())
        porcelain.branch_create(repo.path, new_branch.encode(), repo.refs[base_ref])
    else:
        logger.info("Reusing existing local branch %s", new_branch)
    repo.refs.set_symbolic_ref(b"HEAD", branch_ref)
    porcelain.reset(repo.path, "hard", branch_ref)
    porcelain.checkout_branch(repo, new_branch, force=True)
    repo.refs.set_symbolic_ref(b"HEAD", branch_ref)


def prepare_workspace(
    repo_url: str,
    working_dir: Path,
    change_id: Optional[str] = None,
    branch_name: Optional[str] = None,
) -> CloneResult:
    if not branch_name:
        raise RuntimeError("Branch name must be provided by naming step before clone.")
    target = _get_target_path(repo_url, working_dir, change_id)
    clone_url = _get_clone_url(repo_url)
    token = os.environ.get("GITHUB_TOKEN")
    branch_to_checkout = _get_branch_to_checkout(
        repo_url, token, branch_name, change_id
    )

    repo = load_or_clone_repo(target, repo_url, clone_url)
    fetch_refs(repo, clone_url, repo_url)

    if branch_to_checkout:
        ensure_branch_from_remote(repo, branch_to_checkout, repo_url, token)
        return CloneResult(path=target, branch=branch_to_checkout)

    create_branch_from_default(repo, branch_name, repo_url, token)
    return CloneResult(path=target, branch=branch_name)


def _branch_exists_remotely(
    repo_url: str, change_id: Optional[str], branch_name: Optional[str]
) -> bool:
    token = os.environ.get("GITHUB_TOKEN")
    return _get_branch_to_checkout(repo_url, token, branch_name, change_id) is not None


@dataclass
class WorkspaceRepo(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        branch_name = ctx.state.branches.get(self.repo_url)
        result = prepare_workspace(
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
