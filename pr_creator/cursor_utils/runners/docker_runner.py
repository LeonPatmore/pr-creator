from __future__ import annotations

import docker
import logging
from pathlib import Path
from typing import Any

from pr_creator.cursor_utils.config import (
    get_cursor_env_vars,
    get_cursor_image,
    get_cursor_model,
)
from pr_creator.cursor_utils.runners.base import CursorHintPaths
from pr_creator.cursor_utils.runners.command import build_cursor_agent_command
from pr_creator.cursor_utils.runners.output_log import (
    append_output_log,
    resolve_cursor_output_log,
)
from pr_creator.workspace_mounts import (
    CONTEXT_DIR,
    REPO_DIR,
    WORKSPACE_ROOT,
    workspace_prompt_prefix,
)

logger = logging.getLogger(__name__)


def _build_workspace_volumes(
    repo_abs: str | None, *, context_roots: list[str]
) -> dict[str, dict[str, Any]]:
    """
    Build docker-py `volumes` mapping for an agent container.

    We mount the *target repo* at /workspace/repo (rw) and any extra context roots
    at /workspace/context/<n> (ro).
    """

    volumes: dict[str, dict[str, Any]] = {}

    if repo_abs:
        volumes[repo_abs] = {"bind": REPO_DIR, "mode": "rw"}

    for idx, root in enumerate(context_roots):
        try:
            root_abs = str(Path(root).expanduser().resolve())
        except Exception:
            root_abs = root
        volumes[root_abs] = {"bind": f"{CONTEXT_DIR}/{idx}", "mode": "ro"}

    return volumes


class DockerCursorRunner:
    def __init__(self, *, docker_client: Any | None = None) -> None:
        self._client = docker_client or docker.from_env()

    def hint_paths(
        self, *, repo_abs: str | None, context_roots: list[str]
    ) -> CursorHintPaths:
        # Within the container, the repo is always mounted at /workspace/repo.
        context_dirs = [f"{CONTEXT_DIR}/{idx}" for idx, _ in enumerate(context_roots)]
        return CursorHintPaths(
            repo_dir=REPO_DIR if repo_abs else None, context_dirs=context_dirs
        )

    def run_prompt(
        self,
        prompt: str,
        *,
        intent: str | None = None,
        repo_abs: str | None,
        context_roots: list[str],
        include_repo_hint: bool,
        remove: bool,
        stream_partial_output: bool,
        extra_env: dict[str, str] | None = None,
    ) -> str:
        hint = self.hint_paths(repo_abs=repo_abs, context_roots=context_roots)
        prefix = workspace_prompt_prefix(
            include_repo_hint=include_repo_hint,
            repo_dir=hint.repo_dir,
            context_dirs=hint.context_dirs,
        )
        full_prompt = f"{prefix}{prompt}"

        image = get_cursor_image()
        model = get_cursor_model(intent=intent)
        env_vars = get_cursor_env_vars()
        if extra_env:
            env_vars = {**env_vars, **extra_env}

        volumes = _build_workspace_volumes(repo_abs, context_roots=context_roots)
        workdir = REPO_DIR if repo_abs else WORKSPACE_ROOT

        command = build_cursor_agent_command(
            cli_bin="cursor-agent",
            workspace_root=WORKSPACE_ROOT,
            model=model,
            prompt=full_prompt,
            stream_partial_output=stream_partial_output,
        )

        logger.info(
            "[cursor-runner] runner=docker image=%s model=%s stream_partial_output=%s workdir=%s",
            image,
            model,
            stream_partial_output,
            workdir,
        )

        output_log = resolve_cursor_output_log(
            runner="docker", intent=intent, repo_abs=repo_abs
        )

        output_bytes = self._client.containers.run(
            image,
            command=command,
            volumes=volumes or {},
            working_dir=workdir,
            environment=env_vars,
            remove=remove,
        )
        output = (
            output_bytes.decode("utf-8")
            if isinstance(output_bytes, bytes)
            else str(output_bytes)
        )
        append_output_log(output_log, output or "")
        return output
