from __future__ import annotations

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.create_pull_request import make_create_pull_request_node
from tests.conftest import make_state


def test_creates_pr_and_returns_url(settings, mock_github):
    mock_github.pr_exists.return_value = None
    mock_github.create_pr.return_value = "https://github.com/org/repo/pull/42"

    node = make_create_pull_request_node(mock_github, settings)
    result = node(make_state(
        branch_name="bmad/team-alpha/TEST-10-add-auth",
        current_story_id="TEST-10",
        commit_sha="abc123",
    ))

    assert result["pr_url"] == "https://github.com/org/repo/pull/42"
    mock_github.create_pr.assert_called_once()
    # Default: draft_pr=False → draft=False
    _, kwargs = mock_github.create_pr.call_args
    assert kwargs["draft"] is False


def test_skips_when_pr_already_in_state(settings, mock_github):
    node = make_create_pull_request_node(mock_github, settings)
    result = node(make_state(pr_url="https://github.com/org/repo/pull/1"))

    assert result["pr_url"] == "https://github.com/org/repo/pull/1"
    mock_github.create_pr.assert_not_called()


def test_skips_when_pr_exists_on_github(settings, mock_github):
    mock_github.pr_exists.return_value = "https://github.com/org/repo/pull/7"

    node = make_create_pull_request_node(mock_github, settings)
    result = node(make_state(branch_name="bmad/team/story", commit_sha="abc123"))

    assert result["pr_url"] == "https://github.com/org/repo/pull/7"
    mock_github.create_pr.assert_not_called()


def test_skips_pr_when_no_commit(settings, mock_github):
    """When commit_sha is None (no changes), skip PR creation gracefully."""
    node = make_create_pull_request_node(mock_github, settings)
    result = node(make_state(branch_name="bmad/team/story", commit_sha=None))

    assert result["pr_url"] is None
    assert "No commit" in result["execution_log"][0]["message"]
    mock_github.create_pr.assert_not_called()
    mock_github.pr_exists.assert_not_called()


def test_creates_draft_pr_when_draft_pr_enabled(mock_github):
    draft_settings = Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="test-token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        dry_run=True,
        draft_pr=True,
    )
    mock_github.pr_exists.return_value = None
    mock_github.create_pr.return_value = "https://github.com/org/repo/pull/99"

    node = make_create_pull_request_node(mock_github, draft_settings)
    result = node(make_state(
        branch_name="bmad/team-alpha/TEST-20-new-feature",
        current_story_id="TEST-20",
        commit_sha="abc123",
    ))

    assert result["pr_url"] == "https://github.com/org/repo/pull/99"
    _, kwargs = mock_github.create_pr.call_args
    assert kwargs["draft"] is True
