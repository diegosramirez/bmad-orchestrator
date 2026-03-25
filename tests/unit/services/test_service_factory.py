from __future__ import annotations

from pathlib import Path

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.dummy_github_service import DummyGitHubService
from bmad_orchestrator.services.dummy_jira_service import DummyJiraService
from bmad_orchestrator.services.dummy_slack_service import DummySlackService
from bmad_orchestrator.services.github_service import GitHubService
from bmad_orchestrator.services.jira_service import JiraService
from bmad_orchestrator.services.null_slack_service import NullSlackService
from bmad_orchestrator.services.service_factory import (
    create_github_service,
    create_jira_service,
    create_slack_service,
)
from bmad_orchestrator.services.slack_service import SlackService


def _real_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="test-token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        dry_run=True,
    )


def _dummy_settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        dummy_jira=True,
        dummy_github=True,
        dummy_data_dir=str(tmp_path),
        dry_run=True,
    )


class TestCreateJiraService:
    def test_returns_real_jira_when_dummy_false(self) -> None:
        svc = create_jira_service(_real_settings())
        assert isinstance(svc, JiraService)

    def test_returns_dummy_jira_when_dummy_true(self, tmp_path: Path) -> None:
        svc = create_jira_service(_dummy_settings(tmp_path))
        assert isinstance(svc, DummyJiraService)


class TestCreateGitHubService:
    def test_returns_real_github_when_dummy_false(self) -> None:
        svc = create_github_service(_real_settings())
        assert isinstance(svc, GitHubService)

    def test_returns_dummy_github_when_dummy_true(self, tmp_path: Path) -> None:
        svc = create_github_service(_dummy_settings(tmp_path))
        assert isinstance(svc, DummyGitHubService)


class TestCreateSlackService:
    def test_returns_null_when_notify_false(self) -> None:
        svc = create_slack_service(_real_settings())
        assert isinstance(svc, NullSlackService)

    def test_returns_dummy_when_dummy_jira_and_notify(self, tmp_path: Path) -> None:
        s = Settings(
            anthropic_api_key="test-key",  # type: ignore[arg-type]
            dummy_jira=True,
            dummy_github=True,
            dummy_data_dir=str(tmp_path),
            dry_run=True,
            slack_notify=True,
            slack_bot_token="xoxb-test",  # type: ignore[arg-type]
            slack_channel="#test",
        )
        svc = create_slack_service(s)
        assert isinstance(svc, DummySlackService)

    def test_returns_real_when_notify_and_not_dummy(self) -> None:
        s = Settings(
            anthropic_api_key="test-key",  # type: ignore[arg-type]
            jira_base_url="https://test.atlassian.net",
            jira_username="test@test.com",
            jira_api_token="test-token",  # type: ignore[arg-type]
            jira_project_key="TEST",
            github_repo="org/repo",
            dry_run=True,
            slack_notify=True,
            slack_bot_token="xoxb-test",  # type: ignore[arg-type]
            slack_channel="#test",
        )
        svc = create_slack_service(s)
        assert isinstance(svc, SlackService)
