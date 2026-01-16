from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RepoChangeState:
    """
    State for the repo-change workflow.

    This workflow assumes:
    - it is operating on a single repo (passed as a parameter to the runner)
    - prompt/discovery/orchestration inputs were handled upstream (e.g. orchestrator)
    """

    prompt: str
    working_dir: Path
    # Original base prompt from orchestrator (before repo-specific refinement)
    base_prompt: Optional[str] = None
    # GitHub auth token forwarded from orchestrator (CLI flag wins; otherwise env GITHUB_TOKEN).
    github_token: Optional[str] = None
    context_roots: List[str] = field(default_factory=list)
    # Extra env vars (often secrets) forwarded to the change agent process/container.
    # Values should never be logged.
    change_agent_secrets: Dict[str, str] = field(default_factory=dict)
    cloned: Dict[str, Path] = field(default_factory=dict)
    branches: Dict[str, str] = field(default_factory=dict)
    pr_titles: Dict[str, str] = field(default_factory=dict)
    commit_messages: Dict[str, str] = field(default_factory=dict)
    relevant: List[str] = field(default_factory=list)
    processed: List[str] = field(default_factory=list)
    irrelevant: List[str] = field(default_factory=list)
    # Single PR URL for this repo-change run.
    # SubmitChanges may execute multiple times (e.g., CI-fix loop), but it must always
    # refer to the same PR.
    created_pr: Optional[str] = None
    # The most recent pushed SHA associated with the created PR (if any).
    created_pr_pushed_sha: Optional[str] = None
    # Whether any changes were pushed in the most recent submit
    changes_pushed: bool = False
    # Whether CI checks passed for the PR (None = not waited for, False = failed, True = passed)
    ci_passed: Optional[bool] = None
    change_id: Optional[str] = None
    # Raw review output from the review step, keyed by repo_url.
    review_feedback: Dict[str, str] = field(default_factory=dict)
    # Review feedback that should be applied on the next ApplyChanges pass.
    review_pending: Dict[str, str] = field(default_factory=dict)
    # Number of review->apply retries attempted per repo_url.
    review_attempts: Dict[str, int] = field(default_factory=dict)
    # Number of naming generation attempts per repo_url.
    naming_attempts: Dict[str, int] = field(default_factory=dict)
    # Number of apply (change agent) attempts per repo_url.
    apply_attempts: Dict[str, int] = field(default_factory=dict)
    # CI/action failure output that should be applied on the next ApplyChanges pass.
    ci_pending: Dict[str, str] = field(default_factory=dict)
    # Number of ci->apply retries attempted per repo_url.
    ci_attempts: Dict[str, int] = field(default_factory=dict)
