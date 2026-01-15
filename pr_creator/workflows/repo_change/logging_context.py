from __future__ import annotations

import contextvars
import logging


repo_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "repo_context", default=""
)


class RepoContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        repo = repo_context.get()
        if repo:
            record.repo = f"[{repo}] "
        else:
            record.repo = ""
        return True


def extract_repo_name(repo_url: str) -> str:
    return (
        repo_url.replace("https://github.com/", "")
        .replace("http://github.com/", "")
        .rstrip("/")
    )


def configure_repo_logging() -> None:
    root_logger = logging.getLogger()
    repo_filter = RepoContextFilter()

    for handler in root_logger.handlers:
        if handler.formatter:
            current_format = handler.formatter._fmt
            if "%(repo)s" not in current_format:
                new_format = current_format.replace("%(name)s ", "%(name)s %(repo)s")
                handler.setFormatter(logging.Formatter(new_format))

        if not any(isinstance(f, RepoContextFilter) for f in handler.filters):
            handler.addFilter(repo_filter)

    if not any(isinstance(f, RepoContextFilter) for f in root_logger.filters):
        root_logger.addFilter(repo_filter)
