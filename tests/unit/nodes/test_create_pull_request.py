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


def test_forces_draft_pr_on_failure(settings, mock_github):
    """When failure_state is set, PR is always created as draft regardless of settings."""
    mock_github.pr_exists.return_value = None
    mock_github.create_pr.return_value = "https://github.com/org/repo/pull/55"

    node = make_create_pull_request_node(mock_github, settings)
    result = node(make_state(
        branch_name="bmad/team-alpha/TEST-10-add-auth",
        current_story_id="TEST-10",
        commit_sha="abc123",
        failure_state="Pipeline failed after 2 loop(s). Tests are FAILING.",
        failure_diagnostic="Pipeline exhausted after 2 review loop(s).",
    ))

    assert result["pr_url"] == "https://github.com/org/repo/pull/55"
    _, kwargs = mock_github.create_pr.call_args
    assert kwargs["draft"] is True
    body = kwargs["body"]
    assert "Pipeline Failed" in body
    assert "/bmad retry" in body
    assert "gh workflow run" in body


def test_failure_pr_body_includes_issues_and_diagnostic(settings, mock_github):
    """PR body on failure includes unresolved issues, diagnostic, and resumption instructions."""
    mock_github.pr_exists.return_value = None
    mock_github.create_pr.return_value = "https://github.com/org/repo/pull/60"

    diag = (
        "Pipeline exhausted after 2 review loop(s).\n\n"
        "### Unresolved Issues\n"
        "- **[HIGH]** `src/app.ts`: Missing error handling"
    )
    node = make_create_pull_request_node(mock_github, settings)
    node(make_state(
        branch_name="bmad/team-alpha/TEST-10-add-auth",
        current_story_id="TEST-10",
        commit_sha="abc123",
        failure_state="Pipeline failed after 2 loop(s).",
        failure_diagnostic=diag,
        code_review_issues=[{
            "severity": "high",
            "file": "src/app.ts",
            "line": 42,
            "description": "Missing error handling",
            "fix_required": True,
        }],
    ))

    body = mock_github.create_pr.call_args[1]["body"]
    assert "src/app.ts" in body
    assert "Missing error handling" in body
    assert "bmad/team-alpha/TEST-10-add-auth" in body
    assert "--story-key TEST-10" in body


def test_pr_body_contains_hidden_metadata(settings, mock_github):
    """PR body includes hidden HTML comments with machine-readable metadata."""
    mock_github.pr_exists.return_value = None
    mock_github.create_pr.return_value = "https://github.com/org/repo/pull/70"

    node = make_create_pull_request_node(mock_github, settings)
    node(make_state(
        branch_name="bmad/team-alpha/TEST-10-add-auth",
        current_story_id="TEST-10",
        commit_sha="abc123",
    ))

    body = mock_github.create_pr.call_args[1]["body"]
    assert "<!-- bmad:target_repo=org/repo -->" in body
    assert "<!-- bmad:prompt=Add user authentication -->" in body
    assert "<!-- bmad:team_id=team-alpha -->" in body
