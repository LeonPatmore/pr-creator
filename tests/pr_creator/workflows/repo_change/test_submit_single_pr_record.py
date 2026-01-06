import pytest

from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.submit_step.node import SubmitChanges


@pytest.mark.anyio
async def test_submit_changes_sets_created_pr_once_and_asserts_same_pr(
    monkeypatch, tmp_path
):
    repo_url = "https://github.com/example/example"

    state = RepoChangeState(prompt="p", working_dir=tmp_path)
    state.cloned[repo_url] = tmp_path
    state.branches[repo_url] = "my-branch"
    state.pr_titles[repo_url] = "title"
    state.commit_messages[repo_url] = "msg"

    class _Submitter:
        def __init__(self):
            self.calls = 0

        def submit(self, *_args, **_kwargs):
            self.calls += 1
            # Return the same PR URL on subsequent submits; pushed_sha may change.
            return {
                "repo_url": repo_url,
                "branch": "my-branch",
                "pr_url": "https://github.com/example/example/pull/1",
                "pushed_sha": f"sha-{self.calls}",
            }

    submitter = _Submitter()

    # Patch submitter factory used by the node.
    import pr_creator.workflows.repo_change.submit_step.node as submit_node

    monkeypatch.setattr(
        submit_node, "get_submitter", lambda github_token=None: submitter
    )

    node = SubmitChanges(repo_url=repo_url)

    class _Ctx:
        def __init__(self, state):
            self.state = state

    ctx = _Ctx(state)

    await node.run(ctx)  # type: ignore[arg-type]
    assert state.created_pr == "https://github.com/example/example/pull/1"
    assert state.created_pr_pushed_sha == "sha-1"

    await node.run(ctx)  # type: ignore[arg-type]
    assert state.created_pr == "https://github.com/example/example/pull/1"
    assert state.created_pr_pushed_sha == "sha-2"


@pytest.mark.anyio
async def test_submit_changes_asserts_if_pr_url_changes(monkeypatch, tmp_path):
    repo_url = "https://github.com/example/example"

    state = RepoChangeState(prompt="p", working_dir=tmp_path)
    state.cloned[repo_url] = tmp_path
    state.branches[repo_url] = "my-branch"

    class _Submitter:
        def __init__(self):
            self.calls = 0

        def submit(self, *_args, **_kwargs):
            self.calls += 1
            return {
                "repo_url": repo_url,
                "branch": "my-branch",
                "pr_url": f"https://github.com/example/example/pull/{self.calls}",
            }

    submitter = _Submitter()
    import pr_creator.workflows.repo_change.submit_step.node as submit_node

    monkeypatch.setattr(
        submit_node, "get_submitter", lambda github_token=None: submitter
    )

    node = SubmitChanges(repo_url=repo_url)

    class _Ctx:
        def __init__(self, state):
            self.state = state

    ctx = _Ctx(state)
    await node.run(ctx)  # type: ignore[arg-type]
    assert state.created_pr.endswith("/1")

    with pytest.raises(AssertionError):
        await node.run(ctx)  # type: ignore[arg-type]
