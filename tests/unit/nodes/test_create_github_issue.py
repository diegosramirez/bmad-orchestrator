from __future__ import annotations

from bmad_orchestrator.nodes.create_github_issue import make_create_github_issue_node
from tests.conftest import make_state


def test_creates_issue_and_returns_url(settings, mock_github, mock_jira):
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/42",
        42,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    result = node(make_state(
        current_story_id="TEST-10",
        story_content="Implement user authentication",
        acceptance_criteria=["Users can log in", "Users can log out"],
    ))

    assert result["github_issue_url"] == "https://github.com/org/repo/issues/42"
    assert result["github_issue_number"] == 42
    assert len(result["execution_log"]) == 1
    mock_github.create_issue.assert_called_once()


def test_issue_body_contains_story_content(settings, mock_github, mock_jira):
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state(
        story_content="Implement login flow",
        acceptance_criteria=["AC1", "AC2"],
        architect_output="Use JWT tokens",
        developer_output="Start with auth middleware",
        qa_scope=["Unit tests for login"],
        build_commands=["npm run build"],
        test_commands=["npm test"],
        lint_commands=["npm run lint"],
    ))

    _, kwargs = mock_github.create_issue.call_args
    body = kwargs["body"]
    assert "Implement login flow" in body
    assert "AC1" in body
    assert "Use JWT tokens" in body
    assert "Start with auth middleware" in body
    assert "Unit tests for login" in body
    assert "npm run build" in body
    assert "npm test" in body


def test_issue_title_includes_team_and_story(settings, mock_github, mock_jira):
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/5",
        5,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state(current_story_id="TEST-10"))

    _, kwargs = mock_github.create_issue.call_args
    assert "team-alpha" in kwargs["title"]
    assert "TEST-10" in kwargs["title"]


def test_issue_labels_include_team_id(settings, mock_github, mock_jira):
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state())

    _, kwargs = mock_github.create_issue.call_args
    assert "bmad-orchestrated" in kwargs["labels"]
    assert "team-alpha" in kwargs["labels"]


def test_skips_when_issue_already_exists(settings, mock_github, mock_jira):
    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    result = node(make_state(
        github_issue_url="https://github.com/org/repo/issues/99",
        github_issue_number=99,
    ))

    assert result["github_issue_url"] == "https://github.com/org/repo/issues/99"
    assert result["github_issue_number"] == 99
    mock_github.create_issue.assert_not_called()


def test_posts_jira_comment_with_issue_link(mock_github, mock_jira):
    """When not dry-run, a Jira comment should be posted with the GitHub Issue URL."""
    from bmad_orchestrator.config import Settings

    non_dry_settings = Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="test-token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        dry_run=False,
    )
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/7",
        7,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, non_dry_settings)
    node(make_state(
        current_story_id="TEST-10",
        notify_jira_story_key="TEST-10",
    ))

    mock_jira.add_comment.assert_called_once()
    comment_body = mock_jira.add_comment.call_args[0][1]
    assert "https://github.com/org/repo/issues/7" in comment_body


def test_no_jira_comment_in_dry_run(settings, mock_github, mock_jira):
    """In dry-run mode, no Jira comment should be posted."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state(
        current_story_id="TEST-10",
        notify_jira_story_key="TEST-10",
    ))

    mock_jira.add_comment.assert_not_called()


def test_issue_body_contains_jira_link(settings, mock_github, mock_jira):
    """Issue body should contain a link back to the Jira story."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state(current_story_id="TEST-10"))

    _, kwargs = mock_github.create_issue.call_args
    body = kwargs["body"]
    assert "TEST-10" in body
    assert "test.atlassian.net" in body


def test_handles_missing_optional_fields(settings, mock_github, mock_jira):
    """Node should handle None values for optional state fields gracefully."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    result = node(make_state(
        story_content=None,
        acceptance_criteria=None,
        architect_output=None,
        developer_output=None,
        qa_scope=None,
    ))

    assert result["github_issue_url"] == "https://github.com/org/repo/issues/1"
    # Should not crash — body should contain fallback text
    _, kwargs = mock_github.create_issue.call_args
    body = kwargs["body"]
    assert "N/A" in body or "Not available" in body
