from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.dummy_github_service import DummyGitHubService
from bmad_orchestrator.services.dummy_jira_service import DummyJiraService
from bmad_orchestrator.services.dummy_slack_service import DummySlackService
from bmad_orchestrator.services.github_service import GitHubService
from bmad_orchestrator.services.jira_service import JiraService
from bmad_orchestrator.services.null_slack_service import NullSlackService
from bmad_orchestrator.services.service_factory import (
    build_figma_mcp_config,
    create_github_service,
    create_jira_service,
    create_slack_service,
)
from bmad_orchestrator.services.slack_service import SlackService

_FAKE_PEM = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"


def _real_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="test-token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        github_app_id="12345",
        github_app_installation_id="67890",
        github_app_private_key=_FAKE_PEM,  # type: ignore[arg-type]
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
            github_app_id="12345",
            github_app_installation_id="67890",
            github_app_private_key=_FAKE_PEM,  # type: ignore[arg-type]
            dry_run=True,
            slack_notify=True,
            slack_bot_token="xoxb-test",  # type: ignore[arg-type]
            slack_channel="#test",
        )
        svc = create_slack_service(s)
        assert isinstance(svc, SlackService)


class TestBuildFigmaMcpConfig:
    def test_returns_none_when_disabled(self) -> None:
        assert build_figma_mcp_config(_real_settings()) is None

    def test_returns_http_config_when_enabled(self) -> None:
        s = _real_settings().model_copy(
            update={
                "figma_mcp_enabled": True,
                "figma_mcp_token": SecretStr("figd_abc123"),
            }
        )
        cfg = build_figma_mcp_config(s)
        assert cfg == {
            "figma": {
                "type": "http",
                "url": "https://mcp.figma.com/mcp",
                "headers": {"Authorization": "Bearer figd_abc123"},
            }
        }

    def test_respects_custom_url(self) -> None:
        s = _real_settings().model_copy(
            update={
                "figma_mcp_enabled": True,
                "figma_mcp_url": "https://mcp-staging.figma.com/mcp",
                "figma_mcp_token": SecretStr("figd_xyz"),
            }
        )
        cfg = build_figma_mcp_config(s)
        assert cfg is not None
        assert cfg["figma"]["url"] == "https://mcp-staging.figma.com/mcp"
        assert cfg["figma"]["type"] == "http"

    def test_raises_when_enabled_without_token(self) -> None:
        s = _real_settings().model_copy(update={"figma_mcp_enabled": True})
        import pytest

        with pytest.raises(ValueError, match="BMAD_FIGMA_MCP_TOKEN"):
            build_figma_mcp_config(s)
