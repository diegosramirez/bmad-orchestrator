from __future__ import annotations

import json

from bmad_orchestrator.nodes.create_story_tasks import (
    StoryDraft,
    TaskItem,
    make_create_story_tasks_node,
)
from tests.conftest import make_state


def _make_draft() -> StoryDraft:
    return StoryDraft(
        summary="As a user I want to log in",
        description="Allow users to authenticate.",
        acceptance_criteria=["Can log in with valid creds", "Cannot log in with wrong creds"],
        tasks=[
            TaskItem(summary="Create login endpoint", description="POST /auth/login"),
            TaskItem(summary="Write login tests", description="pytest tests for login"),
        ],
    )


def _make_quality_ok() -> object:
    """Minimal quality gate result (is_clear=True) so refinement is skipped."""
    return type("StoryQualityAssessment", (), {"is_clear": True, "issues": []})()


def test_creates_story_when_none_exists(settings, mock_jira, mock_claude):
    # Node calls complete_structured twice: StoryDraft then StoryQualityAssessment
    mock_claude.complete_structured.side_effect = [_make_draft(), _make_quality_ok()]
    mock_jira.create_story.return_value = {"key": "TEST-10", "summary": "Login story"}
    mock_jira.create_task.return_value = {"key": "TEST-11"}

    node = make_create_story_tasks_node(mock_jira, mock_claude, settings)
    result = node(make_state(current_epic_id="TEST-1"))

    assert result["current_story_id"] == "TEST-10"
    assert result["acceptance_criteria"] == [
        "Can log in with valid creds",
        "Cannot log in with wrong creds",
    ]
    assert mock_jira.create_task.call_count == 2


def test_skips_creation_when_story_already_exists(settings, mock_jira, mock_claude):
    mock_jira.get_story.return_value = {
        "key": "TEST-10",
        "summary": "Login",
        "description": "Existing",
        "status": "To Do",
        "issue_type": "Story",
        "labels": [],
    }

    node = make_create_story_tasks_node(mock_jira, mock_claude, settings)
    result = node(make_state(current_story_id="TEST-10"))

    assert result["current_story_id"] == "TEST-10"
    mock_jira.create_story.assert_not_called()


def test_story_not_found_in_jira_recreates(settings, mock_jira, mock_claude):
    mock_jira.get_story.return_value = None  # stale ID
    mock_claude.complete_structured.side_effect = [_make_draft(), _make_quality_ok()]
    mock_jira.create_story.return_value = {"key": "TEST-20", "summary": "Re-created"}
    mock_jira.create_task.return_value = {"key": "TEST-21"}

    node = make_create_story_tasks_node(mock_jira, mock_claude, settings)
    result = node(make_state(current_story_id="TEST-10", current_epic_id="TEST-1"))

    assert result["current_story_id"] == "TEST-20"


# ── StoryDraft stringified-JSON validator ────────────────────────────────────

def test_story_draft_parses_stringified_acceptance_criteria():
    """StoryDraft should handle acceptance_criteria as a JSON string."""
    raw_ac = json.dumps(["Users can log in", "Invalid creds are rejected"])
    draft = StoryDraft(
        summary="Login story",
        description="Add login",
        acceptance_criteria=raw_ac,
        tasks=[
            TaskItem(summary="Task 1", description="Do thing"),
            TaskItem(summary="Task 2", description="Do other"),
        ],
    )
    assert draft.acceptance_criteria == ["Users can log in", "Invalid creds are rejected"]


def test_story_draft_parses_stringified_tasks():
    """StoryDraft should handle tasks as a JSON string."""
    raw_tasks = json.dumps([
        {"summary": "Task A", "description": "First"},
        {"summary": "Task B", "description": "Second"},
    ])
    draft = StoryDraft(
        summary="Login story",
        description="Add login",
        acceptance_criteria=["AC 1", "AC 2"],
        tasks=raw_tasks,
    )
    assert len(draft.tasks) == 2
    assert draft.tasks[0].summary == "Task A"
