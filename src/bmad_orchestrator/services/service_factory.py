"""Composition root — the single place that decides which service implementation to inject."""

from __future__ import annotations

from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.github_token_provider import GitHubAppTokenProvider
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


def create_github_token_provider(settings: Settings) -> GitHubAppTokenProvider | None:
    """Build a GitHub App token provider, or None when running in dummy mode.

    The provider is shared between ``GitHubService`` and ``GitService`` so they
    hit the same in-memory token cache. Hard-fails on partial App configuration
    rather than silently degrading.
    """
    if settings.dummy_github:
        return None
    missing = [
        name
        for name in ("github_app_id", "github_app_installation_id")
        if getattr(settings, name) is None
    ]
    if (
        settings.github_app_private_key is None
        and settings.github_app_private_key_path is None
    ):
        missing.append("github_app_private_key OR github_app_private_key_path")
    if missing:
        raise ValueError(
            f"GitHub App authentication requires: {', '.join(missing)}"
        )
    assert settings.github_app_id is not None
    assert settings.github_app_installation_id is not None
    return GitHubAppTokenProvider(
        app_id=settings.github_app_id,
        installation_id=settings.github_app_installation_id,
        private_key_pem=settings.resolve_github_app_private_key(),
    )


def create_github_service(
    settings: Settings,
    *,
    token_provider: GitHubAppTokenProvider | None = None,
) -> GitHubServiceProtocol:
    """Return a GitHub service implementation based on settings.

    When ``settings.dummy_github`` is False, a token provider is required;
    callers may pass one to share its cache, or one will be constructed lazily.
    """
    if settings.dummy_github:
        from bmad_orchestrator.services.dummy_github_service import DummyGitHubService

        return DummyGitHubService(settings)

    if token_provider is None:
        token_provider = create_github_token_provider(settings)
    assert token_provider is not None  # not dummy_github → provider always built

    from bmad_orchestrator.services.github_service import GitHubService

    return GitHubService(settings, token_provider=token_provider)


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
