"""Composition root — the single place that decides which service implementation to inject."""

from __future__ import annotations

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.protocols import GitHubServiceProtocol, JiraServiceProtocol


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
