from __future__ import annotations

from pathlib import Path

from dulwich import porcelain

from pr_creator.workflows.orchestrator.evaluate_relevance_step.relevance_cache import (
    DiskRelevanceCache,
    compute_prompt_hash,
    try_get_repo_head_sha,
)


def _commit_one_file(repo_dir: Path, *, filename: str = "file.txt") -> str:
    repo_dir.mkdir(parents=True, exist_ok=True)
    porcelain.init(str(repo_dir))
    (repo_dir / filename).write_text("hello\n", encoding="utf-8")
    porcelain.add(str(repo_dir), [filename])
    commit_sha = porcelain.commit(
        str(repo_dir),
        message=b"init",
        author=b"Test <test@example.com>",
        committer=b"Test <test@example.com>",
        sign=False,
    )
    # dulwich returns raw bytes (20-byte) sha
    if isinstance(commit_sha, (bytes, bytearray)):
        return bytes(commit_sha).hex()
    # Fallback: accept string values if dulwich changes its return type
    return str(commit_sha)


def test_try_get_repo_head_sha_returns_head_commit(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    expected = _commit_one_file(repo_dir)
    got = try_get_repo_head_sha(repo_dir)
    assert got == expected


def test_disk_cache_persists_and_keys_by_repo_sha_prompt(tmp_path: Path) -> None:
    cache_path = tmp_path / "relevance-cache.json"
    cache = DiskRelevanceCache(path=cache_path)

    repo_identifier = "https://github.com/acme/widgets.git"
    sha = "0123456789abcdef0123456789abcdef01234567"
    prompt_hash = compute_prompt_hash("is it relevant?")

    assert (
        cache.get(repo_identifier=repo_identifier, sha=sha, prompt_hash=prompt_hash)
        is None
    )
    cache.set(
        repo_identifier=repo_identifier, sha=sha, prompt_hash=prompt_hash, value=True
    )

    # Reload from disk via a new instance.
    cache2 = DiskRelevanceCache(path=cache_path)
    assert (
        cache2.get(repo_identifier=repo_identifier, sha=sha, prompt_hash=prompt_hash)
        is True
    )

    # Different prompt => miss.
    prompt_hash2 = compute_prompt_hash("different prompt")
    assert (
        cache2.get(repo_identifier=repo_identifier, sha=sha, prompt_hash=prompt_hash2)
        is None
    )

    # Different sha => miss.
    sha2 = "ffffffffffffffffffffffffffffffffffffffff"
    assert (
        cache2.get(repo_identifier=repo_identifier, sha=sha2, prompt_hash=prompt_hash)
        is None
    )
