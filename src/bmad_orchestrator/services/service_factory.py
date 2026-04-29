"""Composition root — the single place that decides which service implementation to inject."""

from __future__ import annotations

from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.protocols import (
    GitHubServiceProtocol,
    JiraServiceProtocol,
    SlackServiceProtocol,
)


def create_jira_service(settings: Settings) -> JiraServiceProtocol:
    """Return a Jira service implementation based on settings."""
    if settings.dummy_jira:
        from bmad_orchestrator.services.dummy_jira_service import DummyJiraService

        return DummyJiraService(settings)

    from bmad_orchestrator.services.jira_service import JiraService

    return JiraService(settings)


def create_github_service(settings: Settings) -> GitHubServiceProtocol:
    """Return a GitHub service implementation based on settings."""
    if settings.dummy_github:
        from bmad_orchestrator.services.dummy_github_service import DummyGitHubService

        return DummyGitHubService(settings)

    from bmad_orchestrator.services.github_service import GitHubService

    return GitHubService(settings)


def build_figma_mcp_config(settings: Settings) -> dict[str, Any] | None:
    """Return the MCP server config dict for the official Figma Dev Mode server.

    Returns None when the integration is disabled. The server runs inside the
    Figma desktop app and is reachable over SSE on the local machine only.
    """
    if not settings.figma_mcp_enabled:
        return None
    return {
        "figma": {
            "type": "sse",
            "url": settings.figma_mcp_url,
        }
    }


def create_slack_service(settings: Settings) -> SlackServiceProtocol:
    """Return a Slack service implementation based on settings."""
    if not settings.slack_notify:
        from bmad_orchestrator.services.null_slack_service import NullSlackService

        return NullSlackService()

    if settings.dummy_jira:
        from bmad_orchestrator.services.dummy_slack_service import DummySlackService

        return DummySlackService(settings)

    from bmad_orchestrator.services.slack_service import SlackService

    return SlackService(settings)
