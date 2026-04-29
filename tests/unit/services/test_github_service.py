from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from bmad_orchestrator.services.github_service import GitHubService, _gh_env


def test_dry_run_create_pr_returns_fake_url(settings, mock_token_provider):
    dry_settings = settings.model_copy(update={"dry_run": True})
    svc = GitHubService(dry_settings, token_provider=mock_token_provider)
    url = svc.create_pr(title="test", body="body", head_branch="feat/x")
    assert url == "https://github.com/dry-run/pulls/0"


def test_create_pr_calls_gh_cli(settings, mock_token_provider):
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="https://github.com/org/repo/pull/5\n", stderr=""
    )
    with patch("bmad_orchestrator.services.github_service._run_gh", return_value=mock_result):
        svc = GitHubService(
            settings.model_copy(update={"dry_run": False}),
            token_provider=mock_token_provider,
        )
        url = svc.create_pr(title="t", body="b", head_branch="branch")
    assert url == "https://github.com/org/repo/pull/5"


def test_pr_exists_returns_none_when_no_output(settings, mock_token_provider):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        svc = GitHubService(settings, token_provider=mock_token_provider)
        assert svc.pr_exists("feature/x") is None


def test_pr_exists_returns_url_when_found(settings, mock_token_provider):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://github.com/org/repo/pull/3\n",
            stderr="",
        )
        svc = GitHubService(settings, token_provider=mock_token_provider)
        assert svc.pr_exists("feature/x") == "https://github.com/org/repo/pull/3"


def test_gh_env_injects_installation_token(mock_token_provider):
    """The provider's installation token should appear as GH_TOKEN in the env."""
    env = _gh_env(mock_token_provider)
    assert env["GH_TOKEN"] == "ghs_test_installation_token"


def test_create_pr_passes_installation_token_to_gh(settings, mock_token_provider):
    """The provider-minted token should be forwarded to the gh subprocess."""
    s = settings.model_copy(update={"dry_run": False})
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://github.com/org/repo/pull/9\n",
            stderr="",
        )
        svc = GitHubService(s, token_provider=mock_token_provider)
        url = svc.create_pr(title="t", body="b", head_branch="feat/x")
    assert url == "https://github.com/org/repo/pull/9"
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["env"]["GH_TOKEN"] == "ghs_test_installation_token"


def test_run_gh_logs_stderr_on_failure(settings, mock_token_provider):
    """CalledProcessError stderr should be logged (not swallowed)."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["gh", "pr", "create"], stderr="HTTP 401: Bad credentials",
        )
        svc = GitHubService(
            settings.model_copy(update={"dry_run": False}),
            token_provider=mock_token_provider,
        )
        with pytest.raises(subprocess.CalledProcessError):
            svc.create_pr(title="t", body="b", head_branch="feat/x")


# ── Issue CRUD tests ──────────────────────────────────────────────────────────


def test_dry_run_create_issue_returns_fake(settings, mock_token_provider):
    dry_settings = settings.model_copy(update={"dry_run": True})
    svc = GitHubService(dry_settings, token_provider=mock_token_provider)
    url, number = svc.create_issue(title="test", body="body")
    assert url == "https://github.com/dry-run/issues/0"
    assert number == 0


def test_create_issue_calls_gh_cli(settings, mock_token_provider):
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout="https://github.com/org/repo/issues/42\n",
        stderr="",
    )
    with patch("bmad_orchestrator.services.github_service._run_gh", return_value=mock_result):
        svc = GitHubService(
            settings.model_copy(update={"dry_run": False}),
            token_provider=mock_token_provider,
        )
        url, number = svc.create_issue(title="t", body="b", labels=["bug", "agent"])
    assert url == "https://github.com/org/repo/issues/42"
    assert number == 42


def test_create_issue_without_labels(settings, mock_token_provider):
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout="https://github.com/org/repo/issues/7\n",
        stderr="",
    )
    with patch(
        "bmad_orchestrator.services.github_service._run_gh", return_value=mock_result,
    ) as mock_gh:
        svc = GitHubService(
            settings.model_copy(update={"dry_run": False}),
            token_provider=mock_token_provider,
        )
        svc.create_issue(title="t", body="b")
    # No --label args should be passed
    call_args = mock_gh.call_args[0][0]
    assert "--label" not in call_args


def test_get_issue(settings, mock_token_provider):
    json_output = '{"number":5,"title":"test","state":"OPEN","body":"body","url":"u","labels":[]}'
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json_output, stderr="",
    )
    with patch("bmad_orchestrator.services.github_service._run_gh", return_value=mock_result):
        svc = GitHubService(settings, token_provider=mock_token_provider)
        data = svc.get_issue(5)
    assert data["number"] == 5
    assert data["state"] == "OPEN"


def test_dry_run_add_issue_comment(settings, mock_token_provider):
    dry_settings = settings.model_copy(update={"dry_run": True})
    svc = GitHubService(dry_settings, token_provider=mock_token_provider)
    # Should not raise
    svc.add_issue_comment(1, "hello")


def test_add_issue_comment_calls_gh(settings, mock_token_provider):
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch(
        "bmad_orchestrator.services.github_service._run_gh", return_value=mock_result,
    ) as mock_gh:
        svc = GitHubService(
            settings.model_copy(update={"dry_run": False}),
            token_provider=mock_token_provider,
        )
        svc.add_issue_comment(10, "comment body")
    call_args = mock_gh.call_args[0][0]
    assert "issue" in call_args
    assert "comment" in call_args
    assert "10" in call_args


def test_dry_run_close_issue(settings, mock_token_provider):
    dry_settings = settings.model_copy(update={"dry_run": True})
    svc = GitHubService(dry_settings, token_provider=mock_token_provider)
    svc.close_issue(1)


def test_close_issue_calls_gh(settings, mock_token_provider):
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch(
        "bmad_orchestrator.services.github_service._run_gh", return_value=mock_result,
    ) as mock_gh:
        svc = GitHubService(
            settings.model_copy(update={"dry_run": False}),
            token_provider=mock_token_provider,
        )
        svc.close_issue(3)
    call_args = mock_gh.call_args[0][0]
    assert "issue" in call_args
    assert "close" in call_args
    assert "3" in call_args
