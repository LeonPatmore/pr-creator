"""Tests for the _strip_markdown_code_fences function in naming_agents."""

from pr_creator.workflows.repo_change.naming_step.naming_agents import (
    _strip_markdown_code_fences,
)


def test_strips_json_code_fence() -> None:
    """Test that markdown code fences with json tag are stripped."""
    input_text = '```json\n{"short_desc": "discourage-production-build-steps"}\n```'
    expected = '{"short_desc": "discourage-production-build-steps"}'
    assert _strip_markdown_code_fences(input_text) == expected


def test_strips_plain_code_fence() -> None:
    """Test that markdown code fences without language tag are stripped."""
    input_text = '```\n{"short_desc": "add-logging"}\n```'
    expected = '{"short_desc": "add-logging"}'
    assert _strip_markdown_code_fences(input_text) == expected


def test_strips_jsonc_code_fence() -> None:
    """Test that markdown code fences with jsonc tag are stripped."""
    input_text = '```jsonc\n{"short_desc": "fix-bug"}\n```'
    expected = '{"short_desc": "fix-bug"}'
    assert _strip_markdown_code_fences(input_text) == expected


def test_returns_plain_json_unchanged() -> None:
    """Test that plain JSON without code fences is returned unchanged."""
    input_text = '{"short_desc": "update-readme"}'
    assert _strip_markdown_code_fences(input_text) == input_text


def test_handles_whitespace_around_fences() -> None:
    """Test that extra whitespace is handled correctly."""
    input_text = '  ```json  \n{"short_desc": "refactor-code"}\n```  '
    expected = '{"short_desc": "refactor-code"}'
    assert _strip_markdown_code_fences(input_text) == expected


def test_handles_multiline_json() -> None:
    """Test that multiline JSON within code fences is preserved."""
    input_text = """```json
{
  "short_desc": "add-feature"
}
```"""
    expected = """{
  "short_desc": "add-feature"
}"""
    assert _strip_markdown_code_fences(input_text) == expected


def test_extracts_json_with_text_before() -> None:
    """Test that JSON is extracted when there's explanatory text before the code fence."""
    input_text = """Update complete. Here is the summary.

Some more text explaining what was done.

```json
{"short_desc": "update-production-deploy-prompt-rules"}
```"""
    expected = '{"short_desc": "update-production-deploy-prompt-rules"}'
    assert _strip_markdown_code_fences(input_text) == expected


def test_extracts_last_code_block_when_multiple_exist() -> None:
    """Test that the last code block is extracted when multiple code blocks exist."""
    input_text = """First some text.

```json
{"short_desc": "wrong-one"}
```

More text in between.

```json
{"short_desc": "correct-one"}
```"""
    expected = '{"short_desc": "correct-one"}'
    assert _strip_markdown_code_fences(input_text) == expected


def test_handles_mixed_content_and_code_blocks() -> None:
    """Test extraction with mixed markdown content."""
    input_text = """## Summary

Updated the base prompt to include:

1. A "Production Deploy Workflows - CRITICAL RULES" section
2. Some bullet points

```json
{"short_desc": "add-critical-production-rules"}
```"""
    expected = '{"short_desc": "add-critical-production-rules"}'
    assert _strip_markdown_code_fences(input_text) == expected
