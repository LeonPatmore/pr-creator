from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PR_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(?:/.*)?$"
)
_ACTIONS_DETAILS_RE = re.compile(
    r"/actions/runs/(?P<run_id>\d+)(?:/job/(?P<job_id>\d+))?"
)


@dataclass(frozen=True)
class CiWaitConfig:
    timeout_seconds: int = 30 * 60
    poll_seconds: int = 15
    max_log_bytes: int = 5_000_000
    max_log_chars: int = 30_000
    acceptable_conclusions: Tuple[str, ...] = ("success", "skipped", "neutral")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except Exception:
        return default


def load_ci_wait_config() -> CiWaitConfig:
    conclusions_raw = os.environ.get(
        "CI_ACCEPTABLE_CONCLUSIONS", "success,skipped,neutral"
    )
    conclusions = tuple(
        c.strip().lower() for c in conclusions_raw.split(",") if c.strip()
    ) or ("success",)
    return CiWaitConfig(
        timeout_seconds=_env_int("CI_WAIT_TIMEOUT_SECONDS", 30 * 60),
        poll_seconds=_env_int("CI_WAIT_POLL_SECONDS", 15),
        max_log_bytes=_env_int("CI_MAX_LOG_BYTES", 5_000_000),
        max_log_chars=_env_int("CI_MAX_LOG_CHARS", 30_000),
        acceptable_conclusions=conclusions,
    )


def parse_pr_url(pr_url: str) -> Optional[Tuple[str, str, int]]:
    m = _PR_URL_RE.match((pr_url or "").strip())
    if not m:
        return None
    return (m.group("owner"), m.group("repo"), int(m.group("number")))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(
    url: str,
    *,
    token: Optional[str],
    accept: str = "application/vnd.github+json",
    timeout: int = 30,
) -> Tuple[int, Dict[str, str], bytes]:
    headers = {"Accept": accept, "User-Agent": "pr-creator"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            hdrs = {k: v for k, v in resp.headers.items()}
            body = resp.read()
            return status, hdrs, body
    except urllib.error.HTTPError as e:
        body = e.read() if hasattr(e, "read") else b""
        hdrs = (
            {k: v for k, v in getattr(e, "headers", {}).items()}
            if getattr(e, "headers", None)
            else {}
        )
        return int(getattr(e, "code", 500)), hdrs, body


def _get_json(url: str, *, token: str) -> Dict[str, Any]:
    status, headers, body = _request(url, token=token)
    if status >= 400:
        raise RuntimeError(
            f"GitHub API request failed ({status}) for {url}: {body[:500]!r}"
        )
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse GitHub JSON response for {url}") from exc


def _get_bytes_follow_redirect(url: str, *, token: str, max_bytes: int) -> bytes:
    status, headers, body = _request(url, token=token)
    if status in (301, 302, 303, 307, 308):
        loc = headers.get("Location") or headers.get("location")
        if not loc:
            raise RuntimeError(
                f"GitHub logs redirect missing Location header for {url}"
            )
        status2, _headers2, body2 = _request(loc, token=None)
        if status2 >= 400:
            raise RuntimeError(
                f"Failed to fetch redirected logs ({status2}) from {loc}"
            )
        return body2[:max_bytes]
    if status >= 400:
        raise RuntimeError(
            f"Failed to fetch logs ({status}) from {url}: {body[:200]!r}"
        )
    return body[:max_bytes]


def _extract_zip_text(data: bytes, *, max_chars: int) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        # Not a zip; treat as text
        return data.decode("utf-8", errors="replace")[:max_chars]

    chunks: list[str] = []
    for name in sorted(zf.namelist()):
        if name.endswith("/"):
            continue
        try:
            raw = zf.read(name)
        except Exception:
            continue
        text = raw.decode("utf-8", errors="replace")
        if text.strip():
            chunks.append(f"--- {name} ---\n{text.rstrip()}\n")
        if sum(len(c) for c in chunks) >= max_chars:
            break

    combined = "\n".join(chunks).strip()
    if len(combined) > max_chars:
        combined = combined[:max_chars].rstrip() + "\n... (truncated)"
    return combined


def _api_base(owner: str, repo: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}"


def get_pr_head_sha(owner: str, repo: str, pr_number: int, *, token: str) -> str:
    pr = _get_json(f"{_api_base(owner, repo)}/pulls/{pr_number}", token=token)
    head = pr.get("head") or {}
    sha = head.get("sha")
    if not sha:
        raise RuntimeError("Unable to determine PR head SHA from GitHub API")
    return str(sha)


def get_check_runs(
    owner: str, repo: str, sha: str, *, token: str
) -> List[Dict[str, Any]]:
    data = _get_json(
        f"{_api_base(owner, repo)}/commits/{sha}/check-runs?per_page=100", token=token
    )
    return list(data.get("check_runs") or [])


def get_combined_status(owner: str, repo: str, sha: str, *, token: str) -> str:
    data = _get_json(f"{_api_base(owner, repo)}/commits/{sha}/status", token=token)
    return str(data.get("state") or "unknown").lower()


def _failed_check_runs(
    check_runs: Iterable[Dict[str, Any]], acceptable_conclusions: Tuple[str, ...]
) -> List[Dict[str, Any]]:
    failed: list[Dict[str, Any]] = []
    for cr in check_runs:
        status = str(cr.get("status") or "").lower()
        if status != "completed":
            continue
        conclusion = str(cr.get("conclusion") or "").lower()
        if conclusion and conclusion not in acceptable_conclusions:
            failed.append(cr)
    return failed


def _has_pending(check_runs: Iterable[Dict[str, Any]], combined_state: str) -> bool:
    if combined_state == "pending":
        return True
    for cr in check_runs:
        status = str(cr.get("status") or "").lower()
        if status in ("queued", "in_progress"):
            return True
    return False


def _parse_actions_ids(details_url: str | None) -> Tuple[Optional[str], Optional[str]]:
    if not details_url:
        return None, None
    m = _ACTIONS_DETAILS_RE.search(details_url)
    if not m:
        return None, None
    return m.group("run_id"), m.group("job_id")


def _filter_check_runs_for_head_sha(
    check_runs: Iterable[Dict[str, Any]], head_sha: str
) -> List[Dict[str, Any]]:
    """
    GitHub check runs are keyed to a specific commit SHA. In practice, we only want
    to evaluate failures for the PR's current head commit, and ignore any failures
    that might appear for previous commits.
    """
    filtered: list[Dict[str, Any]] = []
    for cr in check_runs:
        cr_sha = cr.get("head_sha") or (cr.get("check_suite") or {}).get("head_sha")
        if cr_sha and str(cr_sha) == head_sha:
            filtered.append(cr)
    return filtered


def fetch_failed_logs_snippet(
    owner: str,
    repo: str,
    failed_check_runs: List[Dict[str, Any]],
    *,
    token: str,
    cfg: CiWaitConfig,
) -> str:
    parts: list[str] = []
    for cr in failed_check_runs:
        name = cr.get("name") or cr.get("app", {}).get("name") or "check"
        conclusion = cr.get("conclusion") or "unknown"
        details_url = cr.get("details_url") or ""
        output = cr.get("output") or {}
        summary = (output.get("summary") or "").strip()
        text = (output.get("text") or "").strip()

        parts.append(
            f"### Failed check: {name}\n- conclusion: {conclusion}\n- details: {details_url}\n"
        )
        if summary:
            parts.append(f"#### Output summary\n{summary}\n")
        if text and text != summary:
            parts.append(f"#### Output text\n{text}\n")

        run_id, job_id = _parse_actions_ids(details_url)
        try:
            if job_id:
                data = _get_bytes_follow_redirect(
                    f"{_api_base(owner, repo)}/actions/jobs/{job_id}/logs",
                    token=token,
                    max_bytes=cfg.max_log_bytes,
                )
                extracted = _extract_zip_text(data, max_chars=cfg.max_log_chars)
                if extracted.strip():
                    parts.append("#### Job logs\n" + extracted + "\n")
            elif run_id:
                data = _get_bytes_follow_redirect(
                    f"{_api_base(owner, repo)}/actions/runs/{run_id}/logs",
                    token=token,
                    max_bytes=cfg.max_log_bytes,
                )
                extracted = _extract_zip_text(data, max_chars=cfg.max_log_chars)
                if extracted.strip():
                    parts.append("#### Run logs\n" + extracted + "\n")
        except Exception as exc:
            logger.warning("[ci] failed to download logs for %s: %s", details_url, exc)

    return "\n".join(parts).strip()


def wait_for_ci(
    pr_url: str,
    *,
    token: str,
    cfg: CiWaitConfig,
    expected_head_sha: str | None = None,
) -> Tuple[bool, str]:
    parsed = parse_pr_url(pr_url)
    if not parsed:
        return True, f"[ci] skipping wait: could not parse PR url: {pr_url}"
    owner, repo, pr_number = parsed

    deadline = time.time() + cfg.timeout_seconds
    last_state = "unknown"
    last_counts = ""

    while time.time() < deadline:
        sha = get_pr_head_sha(owner, repo, pr_number, token=token)
        if expected_head_sha and sha != expected_head_sha:
            # Avoid evaluating CI on a stale PR head (GitHub can lag right after a push,
            # or the PR may be pointing at a different head ref than what we just pushed).
            last_state = "waiting_for_pr_head_update"
            last_counts = (
                f"pr_head_sha={sha} expected_head_sha={expected_head_sha} (waiting)"
            )
            time.sleep(cfg.poll_seconds)
            continue
        check_runs_all = get_check_runs(owner, repo, sha, token=token)
        check_runs = _filter_check_runs_for_head_sha(check_runs_all, sha)
        combined_state = get_combined_status(owner, repo, sha, token=token)

        pending = _has_pending(check_runs, combined_state)
        failed = _failed_check_runs(check_runs, cfg.acceptable_conclusions)
        last_state = combined_state
        last_counts = (
            f"checks={len(check_runs)} failed={len(failed)} state={combined_state}"
        )

        if not pending:
            # If there are any checks, require no failures. If there are no checks,
            # treat combined status as the source of truth.
            if check_runs and not failed:
                return True, f"[ci] all checks passed for {pr_url} ({last_counts})"
            if check_runs and failed:
                snippet = fetch_failed_logs_snippet(
                    owner, repo, failed, token=token, cfg=cfg
                )
                return False, (
                    "CI failed for this PR.\n\n"
                    f"- PR: {pr_url}\n"
                    f"- head_sha: {sha}\n"
                    f"- summary: {last_counts}\n\n" + (snippet or "No logs available.")
                )
            # No check runs: rely on combined status.
            if combined_state == "success":
                return (
                    True,
                    f"[ci] no check-runs found; combined status is success for {pr_url}",
                )
            if combined_state in ("failure", "error"):
                return False, (
                    "CI failed for this PR (commit status).\n\n"
                    f"- PR: {pr_url}\n"
                    f"- head_sha: {sha}\n"
                    f"- status: {combined_state}\n"
                )

        time.sleep(cfg.poll_seconds)

    expected_line = (
        f"- expected_head_sha: {expected_head_sha}\n" if expected_head_sha else ""
    )
    return False, (
        "Timed out waiting for CI / GitHub Actions.\n\n"
        f"- PR: {pr_url}\n"
        f"{expected_line}"
        f"- last_state: {last_state}\n"
        f"- last_observed: {last_counts}\n"
    )
