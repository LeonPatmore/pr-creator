## PR Creator

Simple workflow runner that clones target repos, applies changes via a change agent, and submits PRs.

### Use cases
- **Multi-repo rollouts**: apply the same change across many repos (dependency bumps, config standardization, lint/format rules, CI updates).
- **Safe iteration on the same branch**: use `--change-id` so reruns target a stable branch name and you can iterate until the PR is clean.
- **Prompt-config driven automation**: store prompts in a separate “prompt config” repo so changes are reviewed/versioned and rerunnable.
- **Jira-driven prompts**: point at a Jira ticket to build prompts from its summary/description (useful when the ticket is the source of truth).
- **Human-in-the-loop or fully automated**: use human-written prompts, AI change agents, and optional evaluation steps to skip/stop when not relevant.

### Installation
Install from PyPI ([`multi-repo-pr-creator`](https://pypi.org/project/multi-repo-pr-creator/)):

```sh
pip install -U multi-repo-pr-creator
pr-creator --help
```

If you prefer isolated installs:

```sh
pipx install multi-repo-pr-creator
pr-creator --help
```

Quick start (CLI prompts):

```sh
export CURSOR_API_KEY=...
export GITHUB_TOKEN=...

pr-creator \
  --prompt "Update dependency X to version Y." \
  --repo https://github.com/<owner>/<repo> \
  --working-dir .repos
```

Or run via Docker (see example below).

### Docker images
- **pr-creator**: `leonpatmore2/pr-creator:latest` ([Docker Hub](https://hub.docker.com/r/leonpatmore2/pr-creator))
- **cursor-agent**: `leonpatmore2/cursor-agent:latest` ([Docker Hub](https://hub.docker.com/r/leonpatmore2/cursor-agent))

### Required tools
- Either:
  - Docker (to run `cursor-agent` in a container), or
  - A local `cursor-agent` binary on your PATH (to run Cursor via CLI)
- No git or GitHub CLI needed (Dulwich + GitHub API handle clone/push/PR)

### Prompt loading
You choose exactly **one base prompt source**:
- **Inline prompts (CLI)**: pass `--prompt` (required) and optionally `--relevance-prompt`.
  - If `--relevance-prompt` is empty/missing, all repos are treated as relevant.
- **Prompt config YAML (GitHub)**: pass `--prompt-config-owner`, `--prompt-config-repo`, `--prompt-config-path` (and optionally `--prompt-config-ref`).
  - The YAML must include `change_prompt` and `relevance_prompt` (and may include `change_id`).
  - The `relevance_prompt` comes from the YAML (CLI `--relevance-prompt` is ignored in this mode).
- **Jira ticket**: pass `--jira-ticket` (and `--jira-base-url/--jira-email/--jira-api-token` or env fallbacks).
  - The prompt is built from the ticket summary + description.
  - In this mode, `--relevance-prompt` still applies (optional).

**Notes**
- **Mutual exclusion**: you can’t use Jira (`--jira-ticket`) and prompt config (`--prompt-config-*`) together.
- **Prompt “tail”**: if you use prompt config or Jira and also pass `--prompt`, the CLI prompt is appended to the loaded prompt.

### Environment variables
**GitHub auth (required for PR creation)**
- `GITHUB_TOKEN` — used for push and GitHub PR creation.
  - If unset, the workflow can still run, but push/PR creation is skipped.

**Agent selection**
- `CHANGE_AGENT` — choose change agent; default `cursor`.
- `EVALUATE_AGENT` — choose evaluate agent; default `cursor`.
- `NAMING_AGENT` — choose naming agent; default `cursor`.

**Cursor agent runtime (how the change agent is executed)**
- `CURSOR_API_KEY` — passed to the cursor agent.
- `CURSOR_RUNNER` — how to run cursor-agent; `docker` or `cli` (default: `docker`).
- `CURSOR_IMAGE` — docker image for cursor agent; default `leonpatmore2/cursor-agent:latest`.
- `CURSOR_CLI_BIN` — cursor-agent binary name/path when using `CURSOR_RUNNER=cli` (default: `cursor-agent`).
- `CURSOR_WORKSPACE_ROOT` — workspace root passed to cursor-agent when using `CURSOR_RUNNER=cli` (default: common path of repo + context roots).
- `CURSOR_ENV_KEYS` — comma-separated env keys forwarded to the agent; default `CURSOR_API_KEY`.
- `CURSOR_MODEL` — cursor model to use; default `gpt-5.2`.
- `CURSOR_STREAM_MODE` — cursor streaming mode; default `assistant`.
- `CURSOR_STREAM_SHOW_THINKING` — enable showing thinking output; set to `1|true|yes|on` to enable.

**Agent context (optional)**
- `AGENT_CONTEXT_ROOTS` — comma-separated absolute paths on your machine to mount read-only into the agent workspace for extra repo context (available under `/workspace/context/<n>` inside the agent).

**Prompt sources (optional)**
- `JIRA_BASE_URL` — Jira base URL (e.g., https://your-org.atlassian.net) when using `--jira-ticket`.
- `JIRA_EMAIL` — Jira account email for API token auth when using `--jira-ticket`.
- `JIRA_API_TOKEN` — Jira API token when using `--jira-ticket`.

**Repo discovery (optional)**
- `DATADOG_API_KEY` / `DATADOG_APP_KEY` — required if using Datadog repo discovery.
- `GITHUB_DEFAULT_ORG` — default GitHub org/owner to prepend when repo args are provided without an owner (e.g., `--repo my-repo` -> `github.com/<org>/my-repo.git`).

**PR submission & branch naming**
- `SUBMIT_CHANGE` — submitter; default `github`.
- `SUBMIT_PR_BASE` — target base branch; default repo default.
- `SUBMIT_PR_BODY` — PR body; default `Automated changes generated by pr-creator.`
- `DEFAULT_BRANCH_PREFIX` — branch name prefix used when no change_id is provided; default `auto/pr`.

**Logging & git identity**
- `LOG_LEVEL` — logging level; default `INFO`.
- `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` — author/committer; defaults to pr-creator placeholders if unset.

### CLI arguments
**Prompts**
- `--prompt` — main prompt text. Required unless using prompt config.
- `--relevance-prompt` — relevance filter prompt. Required unless using prompt config.

**Jira prompt source**
- `--jira-ticket` — Jira ticket id (e.g., ENG-123) to build the prompt from its summary/description.
- `--jira-base-url` — Jira base URL (env fallback: `JIRA_BASE_URL`).
- `--jira-email` — Jira user email for API token auth (env fallback: `JIRA_EMAIL`).
- `--jira-api-token` — Jira API token (env fallback: `JIRA_API_TOKEN`).
- When using `--jira-ticket`, the change id is automatically set to the Jira ticket id for stable branch names.

**Prompt config (alternative to passing prompts directly)**
- `--prompt-config-owner` — GitHub owner of the prompt config repo. Must be set with `--prompt-config-repo` and `--prompt-config-path`.
- `--prompt-config-repo` — GitHub repo name containing the prompt config file.
- `--prompt-config-ref` — git ref for the prompt config file; default `main`.
- `--prompt-config-path` — path to the YAML prompt config file inside the repo.

**Change ID (for static branches)**
- `--change-id` — Change ID to use for static branch names. When provided, ensures re-runs use the same branch name (format: `{branch_prefix}-{change_id}`). Can also be set in prompt config YAML (takes precedence over CLI arg).

**Repositories**
- `--repo` — repository URL to process. Can be passed multiple times; required if not using Datadog discovery.

**Datadog discovery**
- `--datadog-team` — Datadog team name to discover repos (requires `DATADOG_API_KEY` and `DATADOG_APP_KEY`).
- `--datadog-site` — Datadog API base URL; default `https://api.datadoghq.com`.

**Runtime**
- `--working-dir` — where repos are cloned; default `.repos`.
- `--log-level` — logging level; default `INFO`.
- `--context-root` — host directory to mount (read-only) into the agent workspace for extra context; can be passed multiple times (env equivalent: `AGENT_CONTEXT_ROOTS`).
- `--secret` — forward a secret to the change agent as an env var (`KEY=VALUE`); can be passed multiple times.
- `--secret-env` — forward an env var (by name) from the current process into the change agent; can be passed multiple times.

### Workspace management
- Workspaces live under `--working-dir` (default `.repos`); directories are auto-created per repo.
- When `--change-id` is set, the workspace path is deterministic (`<repo>-<change_id>`) and reused across runs so the same branch can be reapplied.
- Without `--change-id`, a fresh workspace with a random suffix is created and cleaned up after each repo finishes.
- To start fresh, remove the working directory (e.g., `rm -rf .repos`).

### Example (Docker)

```sh
docker run --rm \
  -e CURSOR_API_KEY \
  -e GITHUB_TOKEN \
  leonpatmore2/pr-creator:latest \
  --prompt-config-owner LeonPatmore \
  --prompt-config-repo pr-creator \
  --prompt-config-ref main \
  --prompt-config-path examples/prompt-config.yaml \
  --repo https://github.com/LeonPatmore/cheap-ai-agents-aws \
  --working-dir /tmp/repos \
  --log-level INFO
```

### Developer
**Commands**
- `pipenv run python -m pr_creator.cli --prompt "<prompt>" --relevance-prompt "<relevance>" --repo <repo_url> --working-dir .repos`
- `make test-e2e` — run the e2e pytest (requires env vars set).
- `make lint` — flake8.
- `make format` — black (requires Python ≥3.12.6).
