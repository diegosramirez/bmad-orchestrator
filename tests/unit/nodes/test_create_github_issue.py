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


def test_issue_body_contains_hidden_metadata(settings, mock_github, mock_jira):
    """Issue body should contain hidden HTML comment metadata for the issue-to-code bridge."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state(current_story_id="TEST-10"))

    _, kwargs = mock_github.create_issue.call_args
    body = kwargs["body"]
    assert "<!-- bmad:target_repo=org/repo -->" in body
    assert "<!-- bmad:team_id=team-alpha -->" in body
    assert "<!-- bmad:story_key=TEST-10 -->" in body
    assert "<!-- bmad:base_branch=main -->" in body


def test_auto_execute_adds_bmad_execute_label_from_state(settings, mock_github, mock_jira):
    """When auto_execute_issue is True in state, the bmad-execute label should be added."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state(auto_execute_issue=True))

    _, kwargs = mock_github.create_issue.call_args
    assert "bmad-execute" in kwargs["labels"]


def test_auto_execute_adds_bmad_execute_label_from_settings(mock_github, mock_jira):
    """When auto_execute_issue is True in settings, the bmad-execute label should be added."""
    from bmad_orchestrator.config import Settings

    auto_settings = Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="test-token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        dry_run=True,
        auto_execute_issue=True,
    )
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, auto_settings)
    node(make_state())

    _, kwargs = mock_github.create_issue.call_args
    assert "bmad-execute" in kwargs["labels"]


def test_code_agent_metadata_embedded_when_set(settings, mock_github, mock_jira):
    """When code_agent is set in state, it should appear in hidden metadata."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state(code_agent="copilot"))

    _, kwargs = mock_github.create_issue.call_args
    body = kwargs["body"]
    assert "<!-- bmad:code_agent=copilot -->" in body


def test_code_agent_metadata_absent_when_empty(settings, mock_github, mock_jira):
    """When code_agent is empty (default), no code_agent metadata should be in body."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state())

    _, kwargs = mock_github.create_issue.call_args
    body = kwargs["body"]
    assert "bmad:code_agent" not in body


def test_auto_execute_dispatches_workflow_inline(mock_github, mock_jira):
    """When auto-execute is enabled with inline agent, dispatch_workflow is called."""
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
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, non_dry_settings)
    node(make_state(
        auto_execute_issue=True,
        code_agent="inline",
        current_story_id="TEST-10",
    ))

    mock_github.dispatch_workflow.assert_called_once()
    args = mock_github.dispatch_workflow.call_args
    assert args[0][0] == "bmad-start-run.yml"
    inputs = args[0][1]
    assert inputs["execution_mode"] == "inline"
    assert inputs["skip_check_epic_state"] == "true"
    assert "--story-key TEST-10" in inputs["extra_flags"]
    mock_github.add_issue_comment.assert_called()


def test_auto_execute_copilot_does_not_dispatch_workflow(mock_github, mock_jira):
    """When auto-execute is enabled with copilot agent, no workflow dispatch."""
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
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, non_dry_settings)
    node(make_state(
        auto_execute_issue=True,
        code_agent="copilot",
        current_story_id="TEST-10",
    ))

    mock_github.dispatch_workflow.assert_not_called()
    # Should post a comment about Copilot assignment
    mock_github.add_issue_comment.assert_called_once()


def test_no_auto_execute_label_by_default(settings, mock_github, mock_jira):
    """By default, bmad-execute label should NOT be present."""
    mock_github.create_issue.return_value = (
        "https://github.com/org/repo/issues/1",
        1,
    )

    node = make_create_github_issue_node(mock_github, mock_jira, settings)
    node(make_state())

    _, kwargs = mock_github.create_issue.call_args
    assert "bmad-execute" not in kwargs["labels"]
