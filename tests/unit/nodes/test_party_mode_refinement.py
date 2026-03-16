from __future__ import annotations

import json
from unittest.mock import MagicMock

from bmad_orchestrator.nodes.party_mode_refinement import (
    RefinedStory,
    UserStorySummary,
    make_party_mode_node,
)
from tests.conftest import make_state

# ── RefinedStory stringified-JSON validator ──────────────────────────────────

def test_refined_story_parses_stringified_acceptance_criteria():
    """RefinedStory should handle acceptance_criteria as a JSON string."""
    raw_ac = json.dumps(["Persistence round-trip works", "Meets WCAG AA (4.5:1)."])
    result = RefinedStory(
        updated_summary="Improved story",
        updated_description="Better description",
        acceptance_criteria=raw_ac,
        implementation_notes="Use localStorage",
    )
    assert result.acceptance_criteria == [
        "Persistence round-trip works",
        "Meets WCAG AA (4.5:1).",
    ]


def test_refined_story_accepts_normal_list():
    """RefinedStory should accept a normal list without modification."""
    result = RefinedStory(
        updated_summary="Story",
        updated_description="Desc",
        acceptance_criteria=["AC 1", "AC 2"],
    )
    assert result.acceptance_criteria == ["AC 1", "AC 2"]


# ── project_context injection ─────────────────────────────────────────────────

def test_project_context_injected_into_architect_and_developer_messages(settings):
    """project_context must appear in both architect and developer Claude calls."""
    mock_claude = MagicMock()
    mock_jira = MagicMock()
    mock_claude.complete.return_value = "some feedback"
    mock_claude.complete_structured.return_value = RefinedStory(
        updated_summary="Refined",
        updated_description="Better desc",
        acceptance_criteria=["AC 1"],
        implementation_notes="Use Angular services",
    )

    node = make_party_mode_node(mock_claude, mock_jira, settings)
    node(make_state(
        story_content="Build a todo feature",
        project_context="=== Project Context ===\nFramework: Angular (TypeScript)",
    ))

    complete_calls = mock_claude.complete.call_args_list
    # calls: designer (0), architect (1), developer (2)
    assert "Angular" in complete_calls[1].kwargs["user_message"]  # architect
    assert "Angular" in complete_calls[2].kwargs["user_message"]  # developer


# ── webhook-specific behaviour: title + subtasks ─────────────────────────────


def test_webhook_does_not_touch_title_when_already_user_story(settings):
    """When webhook mode and title already matches format, skip summary update."""
    mock_claude = MagicMock()
    mock_jira = MagicMock()
    mock_claude.complete.return_value = "some feedback"
    mock_claude.complete_structured.return_value = RefinedStory(
        updated_summary="Refined",
        updated_description="Better desc",
        acceptance_criteria=["AC 1"],
        implementation_notes="Use notes",
    )
    mock_jira.get_story.return_value = {
        "key": "PUG-1",
        "summary": "As a user, I want X so that Y.",
    }
    # skip_nodes contains create_story_tasks → webhook mode
    settings = settings.model_copy(update={"skip_nodes": ["create_story_tasks"]})

    node = make_party_mode_node(mock_claude, mock_jira, settings)
    result = node(make_state(current_story_id="PUG-1"))

    mock_jira.update_story_summary.assert_not_called()
    # Still should have normal execution_log
    assert result["execution_log"]


def test_webhook_updates_title_and_creates_subtasks_when_missing(settings):
    """Webhook: fix non-user-story title and create subtasks when none exist."""
    mock_claude = MagicMock()
    mock_jira = MagicMock()
    # Designer/architect/developer outputs
    mock_claude.complete.return_value = "feedback"
    # Structured calls: 1) UserStorySummary (title fix), 2) RefinedStory, 3) _SubtaskList
    mock_claude.complete_structured.side_effect = [
        UserStorySummary(summary="As a user, I want to improve dashboard copy so that it is clearer"),
        RefinedStory(
            updated_summary="Improved",
            updated_description="Refined description",
            acceptance_criteria=["AC 1"],
            implementation_notes="Notes",
        ),
        # For subtasks: schema=_SubtaskList → emulate with simple object
        type("SubtaskList", (), {
            "tasks": [
                type("T", (), {"summary": "Task 1", "description": "Do 1"})(),
                type("T", (), {"summary": "Task 2", "description": "Do 2"})(),
            ]
        })(),
    ]
    mock_jira.get_story.return_value = {
        "key": "PUG-2",
        "summary": "Improve dashboard copy",  # not in user-story format
    }
    mock_jira.get_subtasks.return_value = []  # No existing subtasks

    settings = settings.model_copy(update={"skip_nodes": ["create_story_tasks"]})
    node = make_party_mode_node(mock_claude, mock_jira, settings)
    result = node(make_state(current_story_id="PUG-2"))

    mock_jira.update_story_summary.assert_called_once()
    mock_jira.get_subtasks.assert_called_once_with("PUG-2")
    # Two subtasks created via Jira
    assert mock_jira.create_task.call_count == 2
    assert result["execution_log"]


def test_non_webhook_does_not_call_summary_or_subtasks(settings):
    """When not webhook (skip_nodes does not include create_story_tasks), skip webhook logic."""
    mock_claude = MagicMock()
    mock_jira = MagicMock()
    mock_claude.complete.return_value = "feedback"
    mock_claude.complete_structured.return_value = RefinedStory(
        updated_summary="Refined",
        updated_description="Better desc",
        acceptance_criteria=["AC 1"],
        implementation_notes="Notes",
    )

    # No webhook skip_nodes flag
    node = make_party_mode_node(mock_claude, mock_jira, settings)
    result = node(make_state(current_story_id="PUG-3"))

    mock_jira.get_story.assert_not_called()
    mock_jira.update_story_summary.assert_not_called()
    mock_jira.get_subtasks.assert_not_called()
    mock_jira.create_task.assert_not_called()
    assert result["execution_log"]
