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

from pr_creator.retry_utils import retry_on_exception

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
    heartbeat_seconds: int = 120
    pending_no_checks_grace_seconds: int = 60
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
        heartbeat_seconds=_env_int("CI_WAIT_HEARTBEAT_SECONDS", 120),
        pending_no_checks_grace_seconds=_env_int(
            "CI_PENDING_NO_CHECKS_GRACE_SECONDS", 60
        ),
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
    max_retries: int = 3,
) -> Tuple[int, Dict[str, str], bytes]:
    def _do_request() -> Tuple[int, Dict[str, str], bytes]:
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

    return retry_on_exception(
        _do_request,
        max_retries=max_retries,
        exceptions=(urllib.error.URLError,),
        log_prefix=f"[gh-api] request to {url}",
    )


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


def get_combined_status_and_statuses(
    owner: str, repo: str, sha: str, *, token: str
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Fetch the "combined status" state plus the underlying status contexts.

    This is distinct from check-runs: some CI systems report only commit-status
    contexts (Statuses API) and will never appear as check-runs.
    """
    data = _get_json(f"{_api_base(owner, repo)}/commits/{sha}/status", token=token)
    state = str(data.get("state") or "unknown").lower()
    statuses = list(data.get("statuses") or [])
    return state, statuses


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


def _has_pending(
    check_runs: Iterable[Dict[str, Any]],
    combined_state: str,
    statuses: Iterable[Dict[str, Any]],
) -> bool:
    # Prefer concrete signals over the summary combined_state. GitHub can report
    # combined_state="pending" transiently even when no checks/status contexts
    # have appeared yet.
    for cr in check_runs:
        status = str(cr.get("status") or "").lower()
        if status in ("queued", "in_progress"):
            return True
    for st in statuses:
        if str(st.get("state") or "").lower() == "pending":
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
    start_monotonic = time.monotonic()
    last_heartbeat = 0.0
    pending_without_checks_since: float | None = None
    pending_without_checks_grace_s = float(cfg.pending_no_checks_grace_seconds)

    def _format_check_run(cr: Dict[str, Any]) -> str:
        name = str(cr.get("name") or cr.get("app", {}).get("name") or "check")
        status = str(cr.get("status") or "").lower() or "unknown"
        conclusion = str(cr.get("conclusion") or "").lower() or ""
        details_url = str(cr.get("details_url") or "")
        run_id, job_id = _parse_actions_ids(details_url)
        ids = []
        if run_id:
            ids.append(f"run:{run_id}")
        if job_id:
            ids.append(f"job:{job_id}")
        ids_suffix = f" ({', '.join(ids)})" if ids else ""
        concl = f"/{conclusion}" if conclusion else ""
        return f"{name}={status}{concl}{ids_suffix}"

    def _heartbeat(
        *,
        pr_url: str,
        sha: str,
        combined_state: str,
        check_runs: List[Dict[str, Any]],
        statuses: List[Dict[str, Any]],
        failed: List[Dict[str, Any]],
    ) -> None:
        nonlocal last_heartbeat
        now = time.monotonic()
        if cfg.heartbeat_seconds <= 0:
            return
        if last_heartbeat and (now - last_heartbeat) < cfg.heartbeat_seconds:
            return
        last_heartbeat = now

        elapsed_s = int(now - start_monotonic)
        pending_runs = [
            cr
            for cr in check_runs
            if str(cr.get("status") or "").lower() in ("queued", "in_progress")
        ]
        pending_statuses = [
            st for st in statuses if str(st.get("state") or "").lower() == "pending"
        ]
        pending_preview = ", ".join(_format_check_run(cr) for cr in pending_runs[:6])
        pending_status_preview = ", ".join(
            str(st.get("context") or st.get("description") or "status")[:60]
            for st in pending_statuses[:6]
        )
        failed_preview = ", ".join(_format_check_run(cr) for cr in failed[:4])
        logger.info(
            "[ci] heartbeat: pr=%s sha=%s state=%s pending=%s pending_statuses=%s failed=%s elapsed=%ss%s%s%s",
            pr_url,
            sha[:12],
            combined_state,
            len(pending_runs),
            len(pending_statuses),
            len(failed),
            elapsed_s,
            f" pending_runs=[{pending_preview}]" if pending_preview else "",
            (
                f" pending_statuses=[{pending_status_preview}]"
                if pending_status_preview
                else ""
            ),
            f" failed_runs=[{failed_preview}]" if failed_preview else "",
        )

    while time.time() < deadline:
        sha = get_pr_head_sha(owner, repo, pr_number, token=token)
        if expected_head_sha and sha != expected_head_sha:
            # Avoid evaluating CI on a stale PR head (GitHub can lag right after a push,
            # or the PR may be pointing at a different head ref than what we just pushed).
            last_state = "waiting_for_pr_head_update"
            last_counts = (
                f"pr_head_sha={sha} expected_head_sha={expected_head_sha} (waiting)"
            )
            # Still waiting; emit an occasional heartbeat so long waits are visible.
            if cfg.heartbeat_seconds > 0:
                now = time.monotonic()
                if (
                    not last_heartbeat
                    or (now - last_heartbeat) >= cfg.heartbeat_seconds
                ):
                    last_heartbeat = now
                    elapsed_s = int(now - start_monotonic)
                    logger.info(
                        "[ci] heartbeat: pr=%s state=%s elapsed=%ss (%s)",
                        pr_url,
                        last_state,
                        elapsed_s,
                        last_counts,
                    )
            time.sleep(cfg.poll_seconds)
            continue
        check_runs_all = get_check_runs(owner, repo, sha, token=token)
        check_runs = _filter_check_runs_for_head_sha(check_runs_all, sha)
        combined_state, statuses = get_combined_status_and_statuses(
            owner, repo, sha, token=token
        )

        pending = _has_pending(check_runs, combined_state, statuses)
        failed = _failed_check_runs(check_runs, cfg.acceptable_conclusions)
        last_state = combined_state
        last_counts = (
            f"checks={len(check_runs)} statuses={len(statuses)} failed={len(failed)} "
            f"state={combined_state}"
        )

        # If GitHub claims "pending" but there are no check-runs and no status
        # contexts, we likely have a repo with no CI configured (or a transient
        # API delay). Don't wait forever.
        if (
            combined_state == "pending"
            and not check_runs
            and not statuses
            and pending_without_checks_since is None
        ):
            pending_without_checks_since = time.monotonic()
        if combined_state != "pending" or check_runs or statuses:
            pending_without_checks_since = None

        if (
            pending_without_checks_since is not None
            and (time.monotonic() - pending_without_checks_since)
            >= pending_without_checks_grace_s
        ):
            grace_s = int(pending_without_checks_grace_s)
            return (
                True,
                "[ci] skipping wait: combined status stayed pending for "
                f"{grace_s}s but no checks/statuses were found for {pr_url}",
            )

        # Fail fast: if any checks have failed, exit immediately even if others are pending
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

        # Emit heartbeat if checks are still pending
        if pending or combined_state == "pending":
            _heartbeat(
                pr_url=pr_url,
                sha=sha,
                combined_state=combined_state,
                check_runs=check_runs,
                statuses=statuses,
                failed=failed,
            )

        # All checks complete (no pending, no failures)
        if not pending:
            # If there are any checks and none failed, success
            if check_runs:
                return True, f"[ci] all checks passed for {pr_url} ({last_counts})"
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
