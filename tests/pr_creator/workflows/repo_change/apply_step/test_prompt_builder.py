from __future__ import annotations

from pr_creator.workflows.repo_change.apply_step.prompt_builder import (
    build_change_prompt,
    build_guarded_change_prompt,
    guard_change_agent_prompt,
)


def test_guard_change_agent_prompt_wraps_task():
    guarded = guard_change_agent_prompt("Do the thing")
    assert "# YOUR ROLE" in guarded
    assert "# TASK" in guarded
    assert "Do the thing" in guarded


def test_guard_change_agent_prompt_includes_git_prohibitions():
    guarded = guard_change_agent_prompt("Anything")
    assert "Do NOT commit changes" in guarded
    assert "Do NOT stage changes with git add" in guarded


def test_build_change_prompt_orders_sections_and_includes_base_request():
    prompt = build_change_prompt(
        repo_specific_prompt="Repo prompt",
        base_prompt="Base prompt",
        ci_feedback="CI failed",
        review_feedback="Please change X",
    )
    assert prompt.index("Fix failing CI") < prompt.index("Address review feedback")
    assert "Repo prompt" in prompt
    assert "Original base request" in prompt
    assert "Base prompt" in prompt


def test_build_guarded_change_prompt_includes_guard_and_task():
    prompt = build_guarded_change_prompt(
        repo_specific_prompt="Repo prompt",
        base_prompt=None,
        ci_feedback="",
        review_feedback="",
    )
    assert "# YOUR ROLE" in prompt
    assert "# TASK" in prompt
    assert "Repo prompt" in prompt
