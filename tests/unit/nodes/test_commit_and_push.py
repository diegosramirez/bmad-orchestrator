from __future__ import annotations

from bmad_orchestrator.nodes.commit_and_push import make_commit_and_push_node
from tests.conftest import make_state


def test_commits_and_returns_branch_and_sha(settings, mock_git, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "auth.py").write_text("x = 1")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("x = 1")

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
    assert mock_git.stage_path.call_count == 2
    mock_git.stage_path.assert_any_call("src/api/auth.py")
    mock_git.stage_path.assert_any_call("tests/test_auth.py")
    mock_git.commit.assert_called_once()
    mock_git.push.assert_called_once()


def test_skips_staging_nonexistent_paths(settings, mock_git, tmp_path, monkeypatch):
    """Paths in touched_files that don't exist on disk (e.g. ghost deletes) are skipped."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.py").write_text("x = 1")

    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.commit.return_value = "abc123def456"

    node = make_commit_and_push_node(mock_git, settings)
    node(make_state(
        current_story_id="TEST-10",
        touched_files=["real.py", "ghost/does_not_exist.jsx"],
    ))

    mock_git.stage_path.assert_called_once_with("real.py")


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


def test_dry_run_still_returns_sha(settings, mock_git):
    dry_settings = settings.model_copy(update={"dry_run": True})
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-10-add-auth"
    mock_git.commit.return_value = "dry-run-sha"

    node = make_commit_and_push_node(mock_git, dry_settings)
    result = node(make_state(current_story_id="TEST-10"))

    assert result["commit_sha"] is not None
