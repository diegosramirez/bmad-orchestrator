from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.claude_agent_service import AgentResult
from bmad_orchestrator.state import OrchestratorState


@pytest.fixture
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="test-token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        dry_run=True,
    )


@pytest.fixture
def base_state() -> OrchestratorState:
    return OrchestratorState(
        team_id="team-alpha",
        input_prompt="Add user authentication",
        project_context=None,
        current_epic_id=None,
        current_story_id=None,
        notify_jira_story_key=None,
        step_notification_comment_id=None,
        step_notification_comment_body=None,
        epic_routing_reason=None,
        story_content=None,
        acceptance_criteria=None,
        dependencies=None,
        qa_scope=None,
        definition_of_done=None,
        architect_output=None,
        developer_output=None,
        base_branch=None,
        branch_name=None,
        commit_sha=None,
        pr_url=None,
        github_issue_url=None,
        github_issue_number=None,
        review_loop_count=0,
        code_review_issues=[],
        touched_files=[],
        qa_results=[],
        execution_log=[],
        failure_state=None,
        failure_diagnostic=None,
        slack_thread_ts=None,
        tests_passing=None,
        test_failure_output=None,
        retry_guidance=None,
        build_commands=[],
        test_commands=[],
        lint_commands=[],
        dev_guidelines=None,
    )


@pytest.fixture
def dummy_settings(tmp_path: Any) -> Settings:
    return Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_project_key="DUMMY",
        dummy_jira=True,
        dummy_github=True,
        dummy_data_dir=str(tmp_path / "dummy"),
        dry_run=True,
    )


@pytest.fixture
def mock_jira() -> MagicMock:
    m = MagicMock()
    m.settings = MagicMock(dry_run=False)
    return m


@pytest.fixture
def mock_claude() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_git() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_github() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_slack() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_agent_service() -> MagicMock:
    m = MagicMock()
    m.run_agent.return_value = AgentResult()
    return m


def make_state(**overrides: Any) -> OrchestratorState:
    """Helper: return a base state with given fields overridden."""
    base = OrchestratorState(
        team_id="team-alpha",
        input_prompt="Add user authentication",
        project_context=None,
        current_epic_id=None,
        current_story_id=None,
        notify_jira_story_key=None,
        step_notification_comment_id=None,
        step_notification_comment_body=None,
        epic_routing_reason=None,
        story_content=None,
        acceptance_criteria=None,
        dependencies=None,
        qa_scope=None,
        definition_of_done=None,
        architect_output=None,
        developer_output=None,
        base_branch=None,
        branch_name=None,
        commit_sha=None,
        pr_url=None,
        github_issue_url=None,
        github_issue_number=None,
        review_loop_count=0,
        code_review_issues=[],
        touched_files=[],
        qa_results=[],
        execution_log=[],
        failure_state=None,
        failure_diagnostic=None,
        slack_thread_ts=None,
        tests_passing=None,
        test_failure_output=None,
        retry_guidance=None,
        build_commands=[],
        test_commands=[],
        lint_commands=[],
        dev_guidelines=None,
    )
    return {**base, **overrides}  # type: ignore[return-value]
