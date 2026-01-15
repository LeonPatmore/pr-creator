import logging
from io import StringIO

import pytest

from pr_creator.workflows.repo_change.logging_context import (
    RepoContextFilter,
    extract_repo_name,
    repo_context,
)


def test_extract_repo_name():
    """Test that repo names are correctly extracted from URLs."""
    assert extract_repo_name("https://github.com/owner/repo") == "owner/repo"
    assert extract_repo_name("http://github.com/owner/repo") == "owner/repo"
    assert extract_repo_name("https://github.com/owner/repo/") == "owner/repo"
    assert extract_repo_name("https://github.com/org/my-service") == "org/my-service"


def test_repo_context_filter_no_context():
    """Test that filter works without repo context set."""
    log_filter = RepoContextFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )

    assert log_filter.filter(record) is True
    assert record.repo == ""


def test_repo_context_filter_with_context():
    """Test that filter adds repo context when set."""
    repo_context.set("owner/repo")

    log_filter = RepoContextFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )

    assert log_filter.filter(record) is True
    assert record.repo == "[owner/repo] "

    # Clean up
    repo_context.set("")


def test_logging_integration():
    """Test that repo context appears in formatted log output."""
    # Create a fresh logger for testing
    test_logger = logging.getLogger("test_repo_context")
    test_logger.handlers.clear()
    test_logger.setLevel(logging.INFO)

    # Add handler with our filter
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s %(repo)s%(message)s")
    )
    handler.addFilter(RepoContextFilter())
    test_logger.addHandler(handler)

    # Test without context
    repo_context.set("")
    test_logger.info("No context")

    # Test with context
    repo_context.set("owner/test-repo")
    test_logger.info("With context")

    # Check output
    output = stream.getvalue()
    lines = output.strip().split("\n")

    assert "INFO test_repo_context No context" in lines[0]
    assert "[owner/test-repo]" not in lines[0]

    assert "INFO test_repo_context [owner/test-repo] With context" in lines[1]

    # Clean up
    repo_context.set("")
    test_logger.handlers.clear()


@pytest.mark.anyio
async def test_context_var_isolation():
    """Test that repo_context is properly isolated across async contexts."""
    import asyncio

    results = []

    async def task_with_context(repo_name: str, delay: float):
        repo_context.set(repo_name)
        await asyncio.sleep(delay)
        # Context should be preserved despite async operations
        results.append((repo_name, repo_context.get()))

    # Run multiple tasks concurrently
    await asyncio.gather(
        task_with_context("org/repo-1", 0.1),
        task_with_context("org/repo-2", 0.05),
        task_with_context("org/repo-3", 0.15),
    )

    # Each task should have maintained its own context
    assert ("org/repo-1", "org/repo-1") in results
    assert ("org/repo-2", "org/repo-2") in results
    assert ("org/repo-3", "org/repo-3") in results

    # Clean up
    repo_context.set("")
