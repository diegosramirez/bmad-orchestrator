from __future__ import annotations

from pathlib import Path

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.dummy_github_service import DummyGitHubService
from bmad_orchestrator.services.dummy_jira_service import DummyJiraService
from bmad_orchestrator.services.github_service import GitHubService
from bmad_orchestrator.services.jira_service import JiraService
from bmad_orchestrator.services.service_factory import create_github_service, create_jira_service


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
