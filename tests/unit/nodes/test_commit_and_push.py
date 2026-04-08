from __future__ import annotations

import subprocess

import pytest

from bmad_orchestrator.nodes.commit_and_push import (
    _ensure_pr_retry_workflow,
    make_commit_and_push_node,
)
from tests.conftest import make_state


@pytest.fixture(autouse=True)
def _default_git_preflight(mock_git):
    """Set sane defaults for new pre-flight check methods."""
    mock_git.is_detached_head.return_value = False
    mock_git.has_uncommitted_changes.return_value = False
    mock_git.can_merge_cleanly.return_value = True


def test_commits_and_returns_branch_and_sha(settings, mock_git, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "auth.py").write_text("x = 1")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.commit.return_value = "abc123def456"

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="TEST-10",
        current_epic_id="TEST-1",
        touched_files=["src/api/auth.py", "tests/test_auth.py"],
    ))

    assert result["branch_name"] == "bmad/team-alpha/TEST-10-add-auth"
    assert result["commit_sha"] == "abc123def456"
    # Branch name slug comes from input_prompt, not story_content
    mock_git.make_branch_name.assert_called_once_with(
        "team-alpha", "TEST-10", "Add user authentication"
    )
    mock_git.create_and_checkout_branch.assert_called_once()
    # 2 touched files + 1 auto-installed PR retry forwarder
    assert mock_git.stage_path.call_count == 3
    mock_git.stage_path.assert_any_call("src/api/auth.py")
    mock_git.stage_path.assert_any_call("tests/test_auth.py")
    mock_git.stage_path.assert_any_call(".github/workflows/bmad-pr-retry.yml")
    mock_git.commit.assert_called_once()
    mock_git.push.assert_called_once()


def test_skips_staging_nonexistent_paths(settings, mock_git, tmp_path, monkeypatch):
    """Paths in touched_files that don't exist on disk (e.g. ghost deletes) are skipped."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.commit.return_value = "abc123def456"

    node = make_commit_and_push_node(mock_git, settings)
    node(make_state(
        current_story_id="TEST-10",
        touched_files=["real.py", "ghost/does_not_exist.jsx"],
    ))

    # real.py + auto-installed PR retry forwarder
    mock_git.stage_path.assert_any_call("real.py")
    assert mock_git.stage_path.call_count == 2


def test_skips_staging_paths_outside_repo(settings, mock_git, tmp_path, monkeypatch):
    """Files outside the repo root (e.g. ~/.claude/plans/) must not be staged."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.commit.return_value = "abc123def456"

    node = make_commit_and_push_node(mock_git, settings)
    node(make_state(
        current_story_id="TEST-10",
        touched_files=[
            "real.py",
            "/home/runner/.claude/plans/some-plan.md",
            "/tmp/outside/file.ts",
        ],
    ))

    # real.py + auto-installed PR retry forwarder
    mock_git.stage_path.assert_any_call("real.py")
    assert mock_git.stage_path.call_count == 2


def test_skips_when_already_committed(settings, mock_git):
    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(commit_sha="existing-sha"))

    assert result["commit_sha"] == "existing-sha"
    mock_git.create_and_checkout_branch.assert_not_called()


def test_resume_after_push_failure_no_staged_changes(settings, mock_git, tmp_path, monkeypatch):
    """Retry scenario: commit succeeded in a previous run but push failed.
    has_staged_changes() returns False but HEAD differs from base → proceed to push."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.ts").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.has_staged_changes.return_value = False
    mock_git.get_head_sha.return_value = "be66a71eda58"
    mock_git.rev_parse.return_value = "aaa111bbb222"  # base differs from HEAD

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(current_story_id="TEST-10", touched_files=["app.ts"]))

    assert result["commit_sha"] == "be66a71eda58"
    mock_git.commit.assert_not_called()
    mock_git.get_head_sha.assert_called_once()
    mock_git.push.assert_called_once()


def test_no_changes_skips_commit_and_push(settings, mock_git, tmp_path, monkeypatch):
    """When no files were staged and HEAD equals base, skip commit and push."""
    monkeypatch.chdir(tmp_path)

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.has_staged_changes.return_value = False
    mock_git.get_head_sha.return_value = "same_sha_as_base"
    mock_git.rev_parse.return_value = "same_sha_as_base"

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(current_story_id="TEST-10"))

    assert result["commit_sha"] is None
    assert "No files changed" in result["execution_log"][0]["message"]
    mock_git.commit.assert_not_called()
    mock_git.push.assert_not_called()


def test_empty_commit_on_failure(settings, mock_git, tmp_path, monkeypatch):
    """When failure_state is set and no files changed, create an empty commit for the draft PR."""
    monkeypatch.chdir(tmp_path)

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.has_staged_changes.return_value = False
    mock_git.get_head_sha.return_value = "same_sha"
    mock_git.rev_parse.return_value = "same_sha"
    mock_git.commit.return_value = "empty-commit-sha"

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="TEST-10",
        failure_state="Pipeline failed after 2 loop(s).",
    ))

    assert result["commit_sha"] == "empty-commit-sha"
    mock_git.commit.assert_called_once()
    _, kwargs = mock_git.commit.call_args
    assert kwargs["allow_empty"] is True
    mock_git.push.assert_called_once()


def test_refine_commits_to_existing_bmad_branch(settings, mock_git, tmp_path, monkeypatch):
    """When already on a bmad/ branch (refine), commit to it without creating a new branch."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.ts").write_text("x = 1")

    mock_git.get_current_branch.return_value = "bmad/sam1/SAM1-99-feature"
    mock_git.commit.return_value = "refine123"

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="SAM1-99",
        current_epic_id="SAM1-1",
        touched_files=["app.ts"],
    ))

    assert result["branch_name"] == "bmad/sam1/SAM1-99-feature"
    assert result["base_branch"] == "main"
    mock_git.make_branch_name.assert_not_called()
    mock_git.create_and_checkout_branch.assert_not_called()
    mock_git.commit.assert_called_once()
    mock_git.push.assert_called_once_with("bmad/sam1/SAM1-99-feature")


def test_dry_run_still_returns_sha(settings, mock_git):
    dry_settings = settings.model_copy(update={"dry_run": True})
    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.commit.return_value = "dry-run-sha"

    node = make_commit_and_push_node(mock_git, dry_settings)
    result = node(make_state(current_story_id="TEST-10"))

    assert result["commit_sha"] is not None


# ── Edge case: detached HEAD ──────────────────────────────────────


def test_detached_head_returns_failure_state(settings, mock_git):
    mock_git.is_detached_head.return_value = True

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(current_story_id="TEST-10"))

    assert result["failure_state"]
    assert "detached HEAD" in result["failure_state"]
    mock_git.create_and_checkout_branch.assert_not_called()
    mock_git.push.assert_not_called()


# ── Edge case: push failures ─────────────────────────────────────


def _push_cpe(stderr: str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        1, ["git", "push"], output="", stderr=stderr,
    )


def test_push_auth_failure_returns_failure_state(
    settings, mock_git, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/t/T-1-feat"
    mock_git.commit.return_value = "abc123"
    mock_git.push.side_effect = _push_cpe(
        "Authentication failed for repo",
    )

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="T-1", touched_files=["app.py"],
    ))

    assert result["failure_state"]
    assert "authentication" in result["failure_state"].lower()
    assert result["commit_sha"] == "abc123"
    assert result["branch_name"] == "bmad/t/T-1-feat"


def test_push_network_failure_returns_failure_state(
    settings, mock_git, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/t/T-1-feat"
    mock_git.commit.return_value = "abc123"
    mock_git.push.side_effect = _push_cpe(
        "Could not resolve host: github.com",
    )

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="T-1", touched_files=["app.py"],
    ))

    assert result["failure_state"]
    assert "network" in result["failure_state"].lower()


def test_push_rejected_returns_failure_state(
    settings, mock_git, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/t/T-1-feat"
    mock_git.commit.return_value = "abc123"
    mock_git.push.side_effect = _push_cpe(
        "rejected non-fast-forward",
    )

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="T-1", touched_files=["app.py"],
    ))

    assert result["failure_state"]
    assert "rejected" in result["failure_state"].lower()


# ── Edge case: merge conflict detection ──────────────────────────


def test_merge_conflict_detected_logs_warning(
    settings, mock_git, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/t/T-1-feat"
    mock_git.commit.return_value = "abc123"
    mock_git.can_merge_cleanly.return_value = False

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="T-1", touched_files=["app.py"],
    ))

    assert result["commit_sha"] == "abc123"
    log_msg = result["execution_log"][0]["message"]
    assert "merge conflicts" in log_msg.lower()


# ── Edge case: branch creation failure ────────────────────────────


def test_branch_creation_failure_returns_failure_state(
    settings, mock_git,
):
    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/t/T-1-feat"
    mock_git.create_and_checkout_branch.side_effect = (
        subprocess.CalledProcessError(
            128, ["git", "checkout", "-b"],
            stderr="fatal: cannot lock ref",
        )
    )

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(current_story_id="T-1"))

    assert result["failure_state"]
    assert "branch creation failed" in result["failure_state"].lower()
    mock_git.commit.assert_not_called()
    mock_git.push.assert_not_called()


# ── Edge case: commit failure ─────────────────────────────────────


def test_commit_hook_failure_returns_failure_state(
    settings, mock_git, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("x = 1")

    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/t/T-1-feat"
    mock_git.commit.side_effect = subprocess.CalledProcessError(
        1, ["git", "commit"],
        stderr="pre-commit hook failed",
    )

    node = make_commit_and_push_node(mock_git, settings)
    result = node(make_state(
        current_story_id="T-1", touched_files=["app.py"],
    ))

    assert result["failure_state"]
    assert "pre-commit hook" in result["failure_state"].lower()
    assert result.get("branch_name") == "bmad/t/T-1-feat"
    mock_git.push.assert_not_called()


# ── PR retry forwarder auto-install ──────────────────────────────────────────


def test_ensure_pr_retry_installs_when_missing(tmp_path, mock_git):
    """Forwarder workflow is written and staged when not present."""
    installed = _ensure_pr_retry_workflow(tmp_path, mock_git)
    target = tmp_path / ".github" / "workflows" / "bmad-pr-retry.yml"

    assert installed is True
    assert target.exists()
    assert "BMAD" in target.read_text()
    mock_git.stage_path.assert_called_once_with(".github/workflows/bmad-pr-retry.yml")


def test_ensure_pr_retry_skips_when_present(tmp_path, mock_git):
    """Forwarder workflow is not overwritten if it already exists."""
    target = tmp_path / ".github" / "workflows" / "bmad-pr-retry.yml"
    target.parent.mkdir(parents=True)
    target.write_text("existing content")

    installed = _ensure_pr_retry_workflow(tmp_path, mock_git)

    assert installed is False
    assert target.read_text() == "existing content"
    mock_git.stage_path.assert_not_called()
