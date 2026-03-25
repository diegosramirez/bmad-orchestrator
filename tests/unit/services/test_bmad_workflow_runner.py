from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bmad_orchestrator.services.bmad_workflow_runner import (
    BmadWorkflowRunner,
    load_correct_course_context,
    load_create_epics_and_stories_context,
    load_create_story_context,
)

# ── context loaders ───────────────────────────────────────────────────────────


def test_load_create_epics_missing_files_returns_fallback(settings, monkeypatch, tmp_path):
    """When workflow files don't exist, a non-empty fallback string is returned."""
    monkeypatch.chdir(tmp_path)
    result = load_create_epics_and_stories_context(settings)
    assert "epic" in result.lower()


def test_load_correct_course_missing_files_returns_fallback(settings, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = load_correct_course_context(settings)
    assert "correct-course" in result.lower() or "epic" in result.lower()


def test_load_create_story_missing_files_returns_fallback(settings, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = load_create_story_context(settings)
    assert "story" in result.lower()


def test_load_create_epics_reads_files_when_present(settings, monkeypatch, tmp_path):
    """When workflow files exist, their content is concatenated."""
    monkeypatch.chdir(tmp_path)
    workflow_dir = (
        tmp_path / settings.bmad_root
        / "bmm/workflows/3-solutioning/create-epics-and-stories"
    )
    steps_dir = workflow_dir / "steps"
    steps_dir.mkdir(parents=True)
    (workflow_dir / "workflow.md").write_text("# workflow content")
    (steps_dir / "step-01-validate-prerequisites.md").write_text("# step 01")
    (steps_dir / "step-02-design-epics.md").write_text("# step 02")

    result = load_create_epics_and_stories_context(settings)
    assert "workflow content" in result
    assert "step 01" in result
    assert "step 02" in result


# ── BmadWorkflowRunner ────────────────────────────────────────────────────────


@pytest.fixture
def runner(settings, mock_claude):
    return BmadWorkflowRunner(mock_claude, settings)


def test_run_create_epics_calls_claude(runner, mock_claude, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    schema = MagicMock()
    mock_claude.complete_structured.return_value = MagicMock()

    runner.run_create_epics_and_stories("growth", "Add SSO login", schema)

    mock_claude.complete_structured.assert_called_once()
    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    assert "growth" in call_kwargs["user_message"]
    assert "SSO login" in call_kwargs["user_message"]
    assert call_kwargs["schema"] is schema


def test_run_correct_course_calls_claude(runner, mock_claude, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    schema = MagicMock()
    mock_claude.complete_structured.return_value = MagicMock()

    runner.run_correct_course("PUG-437", "existing desc", "new request", schema)

    mock_claude.complete_structured.assert_called_once()
    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    assert "PUG-437" in call_kwargs["user_message"]
    assert "existing desc" in call_kwargs["user_message"]


def test_run_correct_course_includes_summary(runner, mock_claude, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    schema = MagicMock()
    mock_claude.complete_structured.return_value = MagicMock()

    runner.run_correct_course(
        "PUG-437",
        "existing desc",
        "new request",
        schema,
        existing_summary="My epic title",
    )

    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    assert "My epic title" in call_kwargs["user_message"]
    assert "summary" in call_kwargs["user_message"].lower()


def test_run_discovery_epic_correction_calls_claude(runner, mock_claude, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    schema = MagicMock()
    mock_claude.complete_structured.return_value = MagicMock()

    runner.run_discovery_epic_correction(
        "PUG-437",
        "Title",
        "Desc body",
        "SAM-1",
        schema,
    )

    mock_claude.complete_structured.assert_called_once()
    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    um = call_kwargs["user_message"]
    assert "PUG-437" in um
    assert "Title" in um
    assert "Desc body" in um
    assert "SAM-1" in um
    assert "Discovery Agent" in call_kwargs["system_prompt"] or "Discovery" in um
    assert call_kwargs.get("max_tokens") == 32768


def test_run_create_story_calls_claude(runner, mock_claude, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    schema = MagicMock()
    mock_claude.complete_structured.return_value = MagicMock()

    runner.run_create_story("PUG-437", "growth", "Add login", "ctx", schema)

    mock_claude.complete_structured.assert_called_once()
    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    assert "PUG-437" in call_kwargs["user_message"]
    assert "ctx" in call_kwargs["user_message"]


def test_run_create_story_no_project_context(runner, mock_claude, monkeypatch, tmp_path):
    """Empty project context does not inject a context block."""
    monkeypatch.chdir(tmp_path)
    schema = MagicMock()
    mock_claude.complete_structured.return_value = MagicMock()

    runner.run_create_story("PUG-437", "growth", "Add login", "", schema)

    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    assert "Target project context" not in call_kwargs["user_message"]
