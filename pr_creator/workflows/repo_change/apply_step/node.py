from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo
from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.repo_change.apply_step.change_agents import get_change_agent

logger = logging.getLogger(__name__)

_agent = get_change_agent()


def _build_change_prompt(
    *,
    repo_specific_prompt: str,
    base_prompt: str | None,
    ci_feedback: str,
    review_feedback: str,
) -> str:
    """
    Build the final prompt for the change agent.

    Priority order (highest to lowest):
    1. CI failures (must fix immediately)
    2. Review feedback (must address)
    3. Repo-specific instructions (tailored by orchestrator)
    4. Original base request (context from pr-creator CLI)
    """
    sections: list[str] = []

    if ci_feedback:
        sections.append(
            "## CRITICAL: Fix failing CI / GitHub Actions\n"
            "The PR is failing CI. Use the logs below to fix the issue.\n"
            "If there is a conflict, prioritize this section.\n\n"
            f"{ci_feedback}\n"
        )

    if review_feedback:
        sections.append(
            "## CRITICAL: Address review feedback\n"
            "Apply the following review feedback before doing anything else.\n"
            "If there is a conflict, prioritize this section.\n\n"
            f"{review_feedback}\n"
        )

    sections.append(f"{repo_specific_prompt.strip()}\n")

    if base_prompt and base_prompt.strip() != repo_specific_prompt.strip():
        sections.append(
            "---\n\n"
            "## Original base request (for context)\n"
            f"{base_prompt.strip()}\n"
        )

    return "\n\n".join(sections).rstrip()


def _normalize_eol(data: bytes) -> bytes:
    # Normalize CRLF/CR to LF for comparison.
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _head_blob_bytes(repo: Repo, rel_path: str) -> bytes | None:
    """
    Return the blob bytes for `rel_path` at HEAD, or None if the path does not exist
    in HEAD (e.g., a new file).
    """
    try:
        head_sha = repo.head()
        commit = repo[head_sha]
        tree = repo[commit.tree]
        _mode, blob_sha = tree.lookup_path(repo.get_object, rel_path.encode("utf-8"))
        blob = repo[blob_sha]
        return bytes(getattr(blob, "data", b"") or b"")
    except Exception:
        return None


def _restore_head_file(repo_path: Path, repo: Repo, rel_path: str) -> bool:
    """
    Restore the working tree file at `rel_path` to HEAD. If the file is new (not in HEAD),
    delete it. Returns True if it changed the working tree.
    """
    abs_path = repo_path / rel_path
    head_bytes = _head_blob_bytes(repo, rel_path)
    if head_bytes is None:
        if abs_path.exists():
            try:
                abs_path.unlink()
                return True
            except Exception:
                return False
        return False

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        abs_path.write_bytes(head_bytes)
        return True
    except Exception:
        return False


def _changed_paths(repo_path: Path) -> set[str]:
    st = porcelain.status(str(repo_path))
    paths: set[str] = set()
    # Unstaged is a list of bytes paths.
    for p in getattr(st, "unstaged", []) or []:
        if isinstance(p, bytes):
            paths.add(p.decode("utf-8", errors="replace"))
        else:
            paths.add(str(p))
    # Staged is a dict of lists under keys add/delete/modify (dulwich).
    staged = getattr(st, "staged", {}) or {}
    if isinstance(staged, dict):
        for _k, arr in staged.items():
            for p in arr or []:
                if isinstance(p, bytes):
                    paths.add(p.decode("utf-8", errors="replace"))
                else:
                    paths.add(str(p))
    return paths


def _matches_allowlist(path: str, allow_globs: list[str]) -> bool:
    if not allow_globs:
        return True
    return any(fnmatch(path, g) for g in allow_globs)


def _post_apply_guardrails(repo_path: Path) -> None:
    """
    Enforce safety after the change agent runs:
    - Always revert line-ending-only diffs (CRLF/LF only).
    - Optionally enforce an allowlist (CHANGE_ALLOWED_PATHS) to prevent unrelated file edits.
    """
    repo = Repo.discover(str(repo_path))

    # If the agent staged anything, unstage it so we can reason about working tree state.
    try:
        porcelain.reset(str(repo_path), "mixed", "HEAD")
    except Exception:
        pass

    allow_raw = (os.environ.get("CHANGE_ALLOWED_PATHS") or "").strip()
    allow_globs = [g.strip() for g in allow_raw.split(",") if g.strip()]

    changed = sorted(_changed_paths(repo_path))
    if not changed:
        return

    reverted_allowlist = 0
    reverted_eol_only = 0

    for rel in changed:
        if not _matches_allowlist(rel, allow_globs):
            if _restore_head_file(repo_path, repo, rel):
                reverted_allowlist += 1
            continue

        # For allowed paths, revert if the ONLY difference is line endings.
        head_bytes = _head_blob_bytes(repo, rel)
        abs_path = repo_path / rel
        if head_bytes is None or not abs_path.exists():
            continue
        try:
            work_bytes = abs_path.read_bytes()
        except Exception:
            continue
        if work_bytes != head_bytes and _normalize_eol(work_bytes) == _normalize_eol(
            head_bytes
        ):
            if _restore_head_file(repo_path, repo, rel):
                reverted_eol_only += 1

    if reverted_allowlist:
        logger.info(
            "[apply] reverted %d file(s) outside CHANGE_ALLOWED_PATHS=%r",
            reverted_allowlist,
            allow_raw,
        )
    if reverted_eol_only:
        logger.info("[apply] reverted %d line-ending-only file(s)", reverted_eol_only)


@dataclass
class ApplyChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        logger.info("Applying change agent on %s at %s", self.repo_url, path)

        prompt = _build_change_prompt(
            repo_specific_prompt=ctx.state.prompt,
            base_prompt=ctx.state.base_prompt,
            ci_feedback=ctx.state.ci_pending.pop(self.repo_url, "").strip(),
            review_feedback=ctx.state.review_pending.pop(self.repo_url, "").strip(),
        )

        _agent.run(
            path,
            prompt,
            context_roots=ctx.state.context_roots,
            secrets=ctx.state.change_agent_secrets,
        )
        _post_apply_guardrails(Path(path))
        ctx.state.processed.append(self.repo_url)

        from pr_creator.workflows.repo_change.review_step.node import ReviewChanges

        return ReviewChanges(repo_url=self.repo_url)
