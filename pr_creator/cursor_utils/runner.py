from __future__ import annotations

import docker

from pr_creator.cursor_utils.config import (
    get_cursor_env_vars,
    get_cursor_image,
    get_cursor_model,
)


def run_cursor_prompt(
    prompt: str,
    *,
    volumes: dict | None = None,
    remove: bool = False,
    workdir: str = "/workspace",
) -> str:
    """
    Run cursor-agent with a prompt and return output as str.
    Caller is responsible for binding volumes as needed.
    """
    image = get_cursor_image()
    model = get_cursor_model()
    env_vars = get_cursor_env_vars()
    client = docker.from_env()
    output_bytes = client.containers.run(
        image,
        command=[
            "cursor-agent",
            "--workspace",
            "/workspace",
            "--model",
            model,
            "--print",
            prompt,
        ],
        volumes=volumes or {},
        working_dir=workdir,
        environment=env_vars,
        remove=remove,
    )
    return (
        output_bytes.decode("utf-8")
        if isinstance(output_bytes, bytes)
        else str(output_bytes)
    )
