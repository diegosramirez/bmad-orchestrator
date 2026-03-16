from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from bmad_orchestrator.services.github_service import GitHubService, _gh_env


def test_dry_run_create_pr_returns_fake_url(settings):
    dry_settings = settings.model_copy(update={"dry_run": True})
    svc = GitHubService(dry_settings)
    url = svc.create_pr(title="test", body="body", head_branch="feat/x")
    assert url == "https://github.com/dry-run/pulls/0"


def test_create_pr_calls_gh_cli(settings):
    import subprocess
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="https://github.com/org/repo/pull/5\n", stderr=""
    )
    with patch("bmad_orchestrator.services.github_service._run_gh", return_value=mock_result):
        svc = GitHubService(settings.model_copy(update={"dry_run": False}))
        url = svc.create_pr(title="t", body="b", head_branch="branch")
    assert url == "https://github.com/org/repo/pull/5"


def test_pr_exists_returns_none_when_no_output(settings):
    with patch("subprocess.run") as mock_run:
        import subprocess
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        svc = GitHubService(settings)
        assert svc.pr_exists("feature/x") is None


def test_pr_exists_returns_url_when_found(settings):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://github.com/org/repo/pull/3\n",
            stderr="",
        )
        svc = GitHubService(settings)
        assert svc.pr_exists("feature/x") == "https://github.com/org/repo/pull/3"


def test_gh_env_returns_none_without_token(settings):
    """When no github_token is configured, env should be None (inherit parent)."""
    s = settings.model_copy(update={"github_token": None})
    assert _gh_env(s) is None


def test_gh_env_injects_gh_token(settings):
    """When github_token is set, GH_TOKEN should appear in the env dict."""
    s = settings.model_copy(update={"github_token": SecretStr("ghp_test123")})
    env = _gh_env(s)
    assert env is not None
    assert env["GH_TOKEN"] == "ghp_test123"


def test_create_pr_with_token_passes_env(settings):
    """Token should be forwarded to the gh subprocess."""
    s = settings.model_copy(update={
        "dry_run": False,
        "github_token": SecretStr("ghp_tok"),
    })
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://github.com/org/repo/pull/9\n",
            stderr="",
        )
        svc = GitHubService(s)
        url = svc.create_pr(title="t", body="b", head_branch="feat/x")
    assert url == "https://github.com/org/repo/pull/9"
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["env"]["GH_TOKEN"] == "ghp_tok"


def test_run_gh_logs_stderr_on_failure(settings):
    """CalledProcessError stderr should be logged (not swallowed)."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["gh", "pr", "create"], stderr="HTTP 401: Bad credentials",
        )
        svc = GitHubService(settings.model_copy(update={"dry_run": False}))
        with pytest.raises(subprocess.CalledProcessError):
            svc.create_pr(title="t", body="b", head_branch="feat/x")
