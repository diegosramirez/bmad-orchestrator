from __future__ import annotations

from bmad_orchestrator.config import Settings


def test_settings_with_required_values() -> None:
    s = Settings(
        anthropic_api_key="sk-test",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="user@test.com",
        jira_api_token="token",  # type: ignore[arg-type]
        jira_project_key="PROJ",
        github_repo="org/repo",
        github_base_branch="main",
    )
    assert s.dry_run is False
    assert s.max_review_loops == 2
    assert s.bmad_install_dir == ".claude"
    assert s.github_base_branch == "main"


def test_settings_dry_run_default_false() -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        jira_project_key="P",
        github_repo="o/r",
    )
    assert s.dry_run is False


def test_settings_secret_str_not_logged() -> None:
    s = Settings(
        anthropic_api_key="secret-key",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="secret-token",  # type: ignore[arg-type]
        jira_project_key="P",
        github_repo="o/r",
    )
    assert "secret-key" not in repr(s)
    assert s.anthropic_api_key.get_secret_value() == "secret-key"


def test_settings_model_copy_overrides() -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        jira_project_key="P",
        github_repo="o/r",
    )
    s2 = s.model_copy(update={"dry_run": True, "model_name": "claude-haiku-4.5-20250101"})
    assert s2.dry_run is True
    assert s2.model_name == "claude-haiku-4.5-20250101"
    assert s.dry_run is False  # original unchanged


def test_settings_agent_models_has_defaults() -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        jira_project_key="P",
        github_repo="o/r",
    )
    # Built-in defaults are applied even when user provides no overrides
    assert "pm" in s.agent_models
    assert "build-expert" in s.agent_models


def test_settings_agent_models_user_override_wins() -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        jira_project_key="P",
        github_repo="o/r",
        agent_models={"developer": "claude-haiku-4.5-20250101", "pm": "claude-haiku-4.5-20250101"},
    )
    # User override takes precedence over built-in default
    assert s.agent_models["developer"] == "claude-haiku-4.5-20250101"
    assert s.agent_models["pm"] == "claude-haiku-4.5-20250101"
    # Built-in defaults still present for keys not overridden
    assert "build-expert" in s.agent_models
