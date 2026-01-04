from __future__ import annotations

import io
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from dulwich import porcelain
from dulwich.repo import Repo
from github import Auth, Github

from pr_creator.git_urls import github_slug_from_url, token_auth_github_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloneResult:
    path: Path
    branch: str
    branch_exists_remotely: bool


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sanitize_change_id(change_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in change_id)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-_") or "change"


def get_clone_url(repo_url: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        token_url = token_auth_github_url(repo_url, token)
        if token_url:
            return token_url
    return repo_url


def target_path_for_repo(
    repo_url: str,
    *,
    working_dir: Path,
    change_id: Optional[str],
    stable: bool,
) -> Path:
    """
    Compute a workspace path for a repo.

    - For PR-creation runs, `stable` should be False unless `change_id` is provided.
    - For orchestration planning, `stable` should generally be True (so clones are reused).
    """
    ensure_dir(working_dir)

    # Use owner/repo for nicer stability when possible.
    slug = github_slug_from_url(repo_url)
    if slug:
        name = slug.replace("/", "__").replace("..", ".")
    else:
        name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git") or "repo"

    if change_id:
        safe_id = sanitize_change_id(change_id)
        return working_dir / f"{name}-{safe_id}"

    if stable:
        return working_dir / name

    return working_dir / f"{name}-{uuid.uuid4().hex[:8]}"


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


def fetch_refs(repo: Repo, clone_url: str, repo_url: str) -> Dict[bytes, bytes]:
    try:
        # Silence noisy fetch output, but keep warnings/errors in logs.
        out = io.StringIO()
        err = io.BytesIO()
        remote_refs: Dict[bytes, bytes] = porcelain.fetch(
            repo.path, clone_url, outstream=out, errstream=err
        )

        # dulwich returns refs, but it doesn't always populate remote-tracking refs under
        # refs/remotes/origin/*. Write them so downstream logic can reliably find them.
        written = 0
        for ref_name, sha in remote_refs.items():
            if not ref_name.startswith(b"refs/heads/"):
                continue
            branch_name = ref_name[len(b"refs/heads/") :]
            tracking = b"refs/remotes/origin/" + branch_name
            try:
                repo.refs[tracking] = sha
                written += 1
            except Exception:
                # Best-effort: lack of tracking refs should not break workspaces.
                pass
        if written:
            logger.info(
                "Fetch updated %d origin/* tracking refs for %s", written, repo_url
            )
        return remote_refs
    except Exception as exc:
        logger.warning("Fetch failed for %s: %s", repo_url, exc)
        return {}


def _is_ancestor(repo: Repo, possible_ancestor: bytes, commit_sha: bytes) -> bool:
    """Return True if possible_ancestor is reachable from commit_sha (inclusive)."""
    if possible_ancestor == commit_sha:
        return True
    stack = [commit_sha]
    seen: set[bytes] = set()
    while stack:
        sha = stack.pop()
        if sha in seen:
            continue
        seen.add(sha)
        try:
            obj = repo[sha]
        except Exception:
            continue
        parents = getattr(obj, "parents", None)
        if not parents:
            continue
        for p in parents:
            if p == possible_ancestor:
                return True
            stack.append(p)
    return False


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


def ensure_branch_from_remote(
    repo: Repo, branch: str, repo_url: str, token: Optional[str]
) -> None:
    branch_ref = f"refs/heads/{branch}".encode()
    remote_ref = f"refs/remotes/origin/{branch}".encode()
    local_exists = branch_ref in repo.refs
    remote_exists = remote_ref in repo.refs

    local_sha = repo.refs[branch_ref] if local_exists else None
    remote_sha = repo.refs[remote_ref] if remote_exists else None

    logger.info(
        "Workspace branch refs for %s: local=%s%s remote(origin)=%s%s",
        branch,
        branch_ref.decode(),
        f"@{local_sha.hex()[:8]}" if local_sha else "",
        remote_ref.decode(),
        f"@{remote_sha.hex()[:8]}" if remote_sha else "",
    )

    # Prefer keeping an existing local branch (don't throw away history on reruns).
    if local_exists:
        repo.refs.set_symbolic_ref(b"HEAD", branch_ref)
        porcelain.checkout_branch(repo, branch, force=True)

        if remote_exists:
            if local_sha == remote_sha:
                logger.info("Local branch %s already up to date with origin", branch)
            else:
                # Only move local state when it is a safe fast-forward; otherwise keep local.
                if (
                    local_sha
                    and remote_sha
                    and _is_ancestor(repo, local_sha, remote_sha)
                ):
                    porcelain.reset(repo.path, "hard", remote_sha)
                    repo.refs[branch_ref] = remote_sha
                    logger.info("Fast-forwarded local branch %s to origin", branch)
                elif (
                    local_sha
                    and remote_sha
                    and _is_ancestor(repo, remote_sha, local_sha)
                ):
                    logger.info(
                        "Local branch %s is ahead of remote; keeping local history",
                        branch,
                    )
                else:
                    logger.warning(
                        "Local branch %s has diverged from remote; keeping local history",
                        branch,
                    )
        else:
            logger.warning(
                "Remote tracking ref for branch %s not found; keeping existing local branch",
                branch,
            )
        logger.info("Checked out branch %s", branch)
        return

    if not remote_exists:
        default_branch = _get_default_branch(repo_url, token)
        logger.warning(
            "Remote branch %s not found and no local branch exists; falling back to %s",
            branch,
            default_branch,
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

    # No local branch: create it from the remote-tracking ref.
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
    porcelain.reset(repo.path, "hard", repo.refs[branch_ref])
    porcelain.checkout_branch(repo, new_branch, force=True)
    repo.refs.set_symbolic_ref(b"HEAD", branch_ref)


def make_readonly_best_effort(path: Path) -> None:
    """
    Best-effort: remove write permissions so local tools/agents are less likely
    to mutate the planning workspace.
    """
    try:
        for root, dirs, files in os.walk(path):
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), 0o555)
                except Exception:
                    pass
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), 0o444)
                except Exception:
                    pass
        os.chmod(str(path), 0o555)
    except Exception as exc:
        logger.info("Could not chmod read-only (%s): %s", path, exc)


def prepare_workspace(
    *,
    repo: str,
    working_dir: Path,
    # If provided, prepare a feature-branch workspace suitable for changes.
    branch_name: Optional[str] = None,
    change_id: Optional[str] = None,
    # Planning-mode controls:
    stable: bool = True,
    readonly: bool = False,
) -> CloneResult:
    """
    Shared workspace preparation for both:
    - **planning**: branch_name is None -> read-only inspection workspace (CloneResult; branch="")
    - **changes**: branch_name is set -> feature-branch workspace (CloneResult)
    """
    local = Path(repo).expanduser()
    if local.exists():
        local_abs = local.resolve()
        # Planning can operate directly on a plain directory (no git required).
        if branch_name is None:
            if readonly:
                make_readonly_best_effort(local_abs)
            return CloneResult(path=local_abs, branch="", branch_exists_remotely=False)

        # Change-mode on local paths is intentionally not supported yet (requires
        # careful branch/default-branch semantics without GitHub API).
        raise ValueError(
            "Local repo paths are supported for planning only. "
            "For changes, provide a GitHub repo URL/slug so branch semantics are well-defined."
        )

    # Remote repo: clone into working_dir
    is_change = branch_name is not None
    if is_change:
        target = target_path_for_repo(
            repo, working_dir=working_dir, change_id=change_id, stable=bool(change_id)
        )
    else:
        target = target_path_for_repo(
            repo, working_dir=working_dir, change_id=None, stable=stable
        )
    clone_url = get_clone_url(repo)

    if target.exists() and (target / ".git").exists():
        logger.info(
            "%s reusing clone: %s", "[change]" if is_change else "[plan]", target
        )
        try:
            repo_obj = Repo.discover(str(target))
            fetch_refs(repo_obj, clone_url, repo)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            porcelain.clone(clone_url, str(target), checkout=True)
            repo_obj = Repo.discover(str(target))
    else:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        logger.info(
            "%s cloning %s -> %s", "[change]" if is_change else "[plan]", repo, target
        )
        porcelain.clone(clone_url, str(target), checkout=True)
        repo_obj = Repo.discover(str(target))

    if not is_change:
        if readonly:
            make_readonly_best_effort(target)
        return CloneResult(path=target, branch="", branch_exists_remotely=False)

    # Change mode: ensure we are on the right feature branch.
    assert branch_name is not None
    token = os.environ.get("GITHUB_TOKEN")
    branch_to_checkout = _get_branch_to_checkout(repo, token, branch_name, change_id)
    branch_exists_remotely = branch_to_checkout is not None
    if branch_to_checkout:
        ensure_branch_from_remote(repo_obj, branch_to_checkout, repo, token)
        return CloneResult(
            path=target, branch=branch_to_checkout, branch_exists_remotely=True
        )

    create_branch_from_default(repo_obj, branch_name, repo, token)
    return CloneResult(
        path=target, branch=branch_name, branch_exists_remotely=branch_exists_remotely
    )
