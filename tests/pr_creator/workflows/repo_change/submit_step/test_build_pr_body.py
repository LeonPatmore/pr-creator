from pr_creator.workflows.repo_change.submit_step.github_submitter import _build_pr_body


def test_build_pr_body_with_both_prompts():
    """Test PR body with both base and change prompts."""
    result = _build_pr_body(
        "Default body",
        base_prompt="User wants to add feature X",
        change_prompt="Repo-specific: use module Y",
    )

    assert "Default body" in result
    assert "## Original Request" in result
    assert "User wants to add feature X" in result
    assert "## Repository-Specific Context" in result
    assert "Repo-specific: use module Y" in result


def test_build_pr_body_with_only_base_prompt():
    """Test PR body with only base prompt."""
    result = _build_pr_body(
        "Default body",
        base_prompt="User wants to add feature X",
        change_prompt=None,
    )

    assert "Default body" in result
    assert "## Original Request" in result
    assert "User wants to add feature X" in result
    assert "## Repository-Specific Context" not in result


def test_build_pr_body_with_empty_change_prompt():
    """Test PR body with empty string change prompt."""
    result = _build_pr_body(
        "Default body",
        base_prompt="User wants to add feature X",
        change_prompt="",
    )

    assert "Default body" in result
    assert "## Original Request" in result
    assert "User wants to add feature X" in result
    assert "## Repository-Specific Context" not in result


def test_build_pr_body_with_only_change_prompt():
    """Test PR body with only change prompt (orchestrator didn't provide base)."""
    result = _build_pr_body(
        "Default body",
        base_prompt=None,
        change_prompt="Repo-specific instructions",
    )

    assert "Default body" in result
    assert "## Original Request" not in result
    assert "## Repository-Specific Context" in result
    assert "Repo-specific instructions" in result


def test_build_pr_body_with_no_prompts():
    """Test PR body with no prompts at all."""
    result = _build_pr_body(
        "Default body",
        base_prompt=None,
        change_prompt=None,
    )

    assert result == "Default body"
    assert "## Original Request" not in result
    assert "## Repository-Specific Context" not in result
