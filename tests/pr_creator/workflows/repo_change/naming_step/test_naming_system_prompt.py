from __future__ import annotations

from pr_creator.workflows.repo_change.naming_step.system_prompt_builder import (
    build_naming_system_prompt,
)


def test_system_prompt_structure():
    """Verify the system prompt is clear and actionable."""
    prompt = build_naming_system_prompt()

    # Should include key sections
    assert "# ROLE" in prompt
    assert "# TASK" in prompt
    assert "# OUTPUT REQUIREMENTS" in prompt
    assert "# GUIDANCE" in prompt
    assert "# EXAMPLES" in prompt

    # Should have clear task instructions
    assert "Read the user's change description" in prompt
    assert "generate a short kebab-case name" in prompt

    # Should use User/Assistant format in examples (not Prompt/Output)
    assert "User:" in prompt
    assert "Assistant:" in prompt

    # Should have kebab-case output requirements
    assert "kebab-case" in prompt
    assert "lowercase" in prompt
    assert "3-6 words" in prompt


def test_system_prompt_examples_are_valid():
    """Verify all example outputs follow the stated rules."""
    prompt = build_naming_system_prompt()

    # Extract example outputs (lines that follow "Assistant:")
    lines = prompt.split("\n")
    examples = []
    for i, line in enumerate(lines):
        if line.startswith("Assistant:"):
            examples.append(line.replace("Assistant:", "").strip())

    assert len(examples) > 0, "Should have at least one example"

    for example in examples:
        # Must be lowercase
        assert example == example.lower(), f"Example '{example}' should be lowercase"

        # Must be kebab-case (only letters, numbers, hyphens)
        assert all(
            c.isalnum() or c == "-" for c in example
        ), f"Example '{example}' should only contain letters, numbers, and hyphens"

        # Should have 3-6 words (count hyphens + 1)
        word_count = example.count("-") + 1
        assert (
            3 <= word_count <= 6
        ), f"Example '{example}' has {word_count} words, expected 3-6"
