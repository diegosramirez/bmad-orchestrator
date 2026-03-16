from __future__ import annotations

from unittest.mock import MagicMock, patch

from bmad_orchestrator.services.git_service import GitService, _slugify


def test_slugify_lowercases_and_replaces_spaces(settings):
    assert _slugify("Add User Auth") == "add-user-auth"


def test_slugify_removes_special_chars(settings):
    assert _slugify("Fix bug: null pointer!") == "fix-bug-null-pointer"


def test_slugify_truncates_to_max_len(settings):
    long_text = "a" * 100
    result = _slugify(long_text, max_len=20)
    assert len(result) <= 20


def test_make_branch_name_format(settings):
    svc = GitService(settings)
    branch = svc.make_branch_name("growth", "DS24-42", "Add user auth")
    assert branch == "bmad/growth/DS24-42-add-user-auth"


def test_make_branch_name_sanitizes_team_id(settings):
    svc = GitService(settings)
    branch = svc.make_branch_name(
        "It doesn't work! Fix it, please.", "DUMMY-41", "test"
    )
    assert " " not in branch
    assert "'" not in branch
    assert "!" not in branch
    assert "," not in branch
    # _slugify truncates to max_len=20 and strips trailing hyphens
    assert branch.startswith("bmad/it-doesn-t-work-fix/")


def test_dry_run_commit_returns_fake_sha(settings):
    dry_settings = settings.model_copy(update={"dry_run": True})
    svc = GitService(dry_settings)
    sha = svc.commit("msg")
    assert sha == "dry-run-sha"


def test_dry_run_push_skips(settings):
    dry_settings = settings.model_copy(update={"dry_run": True})
    svc = GitService(dry_settings)
    # Should not raise even though git is not available in test env
    result = svc.push("some-branch")
    assert result is None


# ── real subprocess paths ─────────────────────────────────────────────────────

def _live(settings):
    return settings.model_copy(update={"dry_run": False})


def test_get_current_branch(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")
        assert svc.get_current_branch() == "main"


def test_branch_exists_remote_true(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="refs/heads/main\n", returncode=0)
        assert svc.branch_exists_remote("main") is True


def test_branch_exists_remote_false(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        assert svc.branch_exists_remote("ghost") is False


def test_create_and_checkout_branch_new(settings):
    svc = GitService(_live(settings))
    # ls-remote returns empty → branch doesn't exist → checkout -b
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        svc.create_and_checkout_branch("bmad/pug/PUG-1-auth")
    assert mock_run.call_count >= 1


def test_create_and_checkout_branch_existing_remote(settings):
    svc = GitService(_live(settings))
    responses = [
        MagicMock(stdout="refs/heads/bmad/pug/PUG-1\n", returncode=0),  # ls-remote
        MagicMock(returncode=0, stdout="", stderr=""),                   # git fetch
        MagicMock(returncode=0, stdout="", stderr=""),                   # git checkout
    ]
    with patch("bmad_orchestrator.services.git_service.subprocess.run", side_effect=responses):
        svc.create_and_checkout_branch("bmad/pug/PUG-1")


def test_create_and_checkout_branch_existing_local(settings):
    """Retry scenario: branch exists locally but not on remote.
    checkout -b raises 'already exists' → falls back to plain checkout."""
    import subprocess as _sp
    svc = GitService(_live(settings))

    already_exists_exc = _sp.CalledProcessError(
        returncode=128,
        cmd=["git", "checkout", "-b", "bmad/pug/PUG-1"],
        output="",
        stderr="fatal: a branch named 'bmad/pug/PUG-1' already exists\n",
    )
    responses = [
        MagicMock(stdout="", returncode=0),   # ls-remote → not on remote
        already_exists_exc,                    # checkout -b → fails
        MagicMock(returncode=0, stdout="", stderr=""),  # checkout → succeeds
    ]
    mock_target = "bmad_orchestrator.services.git_service.subprocess.run"
    with patch(mock_target, side_effect=responses) as mock_run:
        svc.create_and_checkout_branch("bmad/pug/PUG-1")
    # Plain checkout (not -b) must have been the last call
    last_call_args = mock_run.call_args_list[-1][0][0]
    assert last_call_args == ["git", "checkout", "bmad/pug/PUG-1"]


def test_stage_path(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        svc.stage_path("_bmad-output/implementation-artifacts/STORY-1")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args == ["git", "add", "--", "_bmad-output/implementation-artifacts/STORY-1"]


def test_commit_real_path(settings):
    svc = GitService(_live(settings))
    responses = [
        MagicMock(returncode=0, stdout="", stderr=""),          # git commit
        MagicMock(returncode=0, stdout="abc123def\n", stderr=""),  # git rev-parse HEAD
    ]
    with patch("bmad_orchestrator.services.git_service.subprocess.run", side_effect=responses):
        sha = svc.commit("test commit")
    assert sha == "abc123def"


def test_has_staged_changes_true(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)  # 1 = staged changes exist
        assert svc.has_staged_changes() is True


def test_has_staged_changes_false(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)  # 0 = index clean
        assert svc.has_staged_changes() is False


def test_get_head_sha(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="deadbeef12\n", stderr="")
        sha = svc.get_head_sha()
    assert sha == "deadbeef12"


def test_push_real_path(settings):
    svc = GitService(_live(settings))
    with patch("bmad_orchestrator.services.git_service.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        svc.push("bmad/pug/PUG-1")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args == ["git", "push", "-u", "origin", "HEAD:refs/heads/bmad/pug/PUG-1"]
