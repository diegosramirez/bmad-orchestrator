from __future__ import annotations

import json

from bmad_orchestrator.nodes.create_story_tasks import (
    EpicStoryBreakdown,
    PlannedStoryItem,
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


def _epic_with_discovery() -> dict:
    return {
        "key": "TEST-1",
        "summary": "Epic",
        "description": "# Discovery\n\nSome discovery text.",
    }


def test_stories_breakdown_creates_multiple_stories(settings, mock_jira, mock_claude):
    sb = settings.model_copy(update={"execution_mode": "stories_breakdown"})
    mock_jira.get_epic.return_value = _epic_with_discovery()
    mock_jira.list_stories_under_epic.return_value = []
    breakdown = EpicStoryBreakdown(
        stories=[
            PlannedStoryItem(
                summary="As a user I want feature alpha so that I succeed",
                description="**Hypothesis**\nH1\n\n**Intervention**\nI1",
                acceptance_criteria=["AC a1", "AC a2"],
                tasks=[],
            ),
            PlannedStoryItem(
                summary="As a user I want feature beta so that I win",
                description="**Hypothesis**\nH2\n\n**Intervention**\nI2",
                acceptance_criteria=["AC b1", "AC b2"],
                tasks=[
                    TaskItem(summary="Sub 1", description="Do 1"),
                    TaskItem(summary="Sub 2", description="Do 2"),
                ],
            ),
        ]
    )
    mock_claude.complete_structured.return_value = breakdown
    mock_jira.create_story.side_effect = [
        {"key": "TEST-10", "summary": breakdown.stories[0].summary},
        {"key": "TEST-11", "summary": breakdown.stories[1].summary},
    ]
    mock_jira.create_task.return_value = {"key": "TEST-12"}
    mock_jira.get_story.return_value = {
        "key": "TEST-11",
        "description": "**Acceptance Criteria:**\n- AC b1\n- AC b2\n",
    }

    node = make_create_story_tasks_node(mock_jira, mock_claude, sb)
    result = node(
        make_state(current_epic_id="TEST-1", team_id="growth", input_prompt="TEST-1"),
    )

    assert result["created_story_ids"] == ["TEST-10", "TEST-11"]
    assert result["current_story_id"] == "TEST-11"
    assert mock_jira.create_story.call_count == 2
    assert mock_jira.create_task.call_count == 2


def test_stories_breakdown_skips_duplicate_against_existing(settings, mock_jira, mock_claude):
    sb = settings.model_copy(update={"execution_mode": "stories_breakdown"})
    mock_jira.get_epic.return_value = _epic_with_discovery()
    mock_jira.list_stories_under_epic.return_value = [
        {"summary": "As a user I want feature alpha so that I succeed", "key": "TEST-99"},
    ]
    breakdown = EpicStoryBreakdown(
        stories=[
            PlannedStoryItem(
                summary="As a user I want feature alpha so that I succeed",
                description="Dup",
                acceptance_criteria=["AC 1", "AC 2"],
                tasks=[],
            ),
            PlannedStoryItem(
                summary="As a user I want only new work so that it ships",
                description="**Hypothesis**\nH\n\n**Intervention**\nI",
                acceptance_criteria=["AC n1", "AC n2"],
                tasks=[],
            ),
        ]
    )
    mock_claude.complete_structured.return_value = breakdown
    mock_jira.create_story.return_value = {
        "key": "TEST-20",
        "summary": breakdown.stories[1].summary,
    }
    mock_jira.get_story.return_value = {
        "key": "TEST-20",
        "description": "**Acceptance Criteria:**\n- AC n1\n- AC n2\n",
    }

    node = make_create_story_tasks_node(mock_jira, mock_claude, sb)
    result = node(make_state(current_epic_id="TEST-1", team_id="growth"))

    assert result["created_story_ids"] == ["TEST-20"]
    assert mock_jira.create_story.call_count == 1
