from __future__ import annotations

from pathlib import Path

from pr_creator.repo_workspace import CloneResult, prepare_workspace


def test_prepare_workspace_planning_mode_returns_cloneresult_for_local_dir(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "README.md").write_text("hello\n", encoding="utf-8")

    result = prepare_workspace(repo=str(repo_dir), working_dir=tmp_path / "ignored")
    assert isinstance(result, CloneResult)
    assert result.path == repo_dir.resolve()
    assert result.branch == ""
