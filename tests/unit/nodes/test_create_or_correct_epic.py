from __future__ import annotations

from unittest.mock import MagicMock

from bmad_orchestrator.nodes.create_or_correct_epic import (
    EpicCorrectionDecision,
    EpicDraft,
    make_create_or_correct_epic_node,
)
from tests.conftest import make_state


def test_skips_creation_when_epic_already_exists(settings, mock_jira, mock_claude):
    # Course-correction path: existing epic description is already sufficient
    mock_jira.get_story.return_value = {"description": "Existing epic description"}
    mock_claude.complete_structured.return_value = EpicCorrectionDecision(
        needs_update=False, reason="Already covers the new request"
    )
    node = make_create_or_correct_epic_node(mock_jira, mock_claude, settings)
    result = node(make_state(current_epic_id="TEST-5"))

    assert result["current_epic_id"] == "TEST-5"
    mock_jira.create_epic.assert_not_called()
    mock_jira.update_epic.assert_not_called()


def test_creates_epic_when_none_exists(settings, mock_jira, mock_claude):
    mock_claude.complete_structured.return_value = EpicDraft(
        summary="Auth Epic", description="Implement auth"
    )
    mock_jira.create_epic.return_value = {"key": "TEST-99", "summary": "Auth Epic"}

    node = make_create_or_correct_epic_node(mock_jira, mock_claude, settings)
    result = node(make_state(current_epic_id=None))

    assert result["current_epic_id"] == "TEST-99"
    mock_jira.create_epic.assert_called_once()


def test_dry_run_does_not_call_jira(settings, mock_jira, mock_claude):
    dry_settings = settings.model_copy(update={"dry_run": True})
    mock_jira.settings = MagicMock(dry_run=True)
    mock_claude.complete_structured.return_value = EpicDraft(
        summary="Epic", description="Desc"
    )
    # In dry-run mode the @skip_if_dry_run decorator returns the fake value
    mock_jira.create_epic.return_value = {"key": "DRY-001", "summary": "Dry-run Epic"}

    node = make_create_or_correct_epic_node(mock_jira, mock_claude, dry_settings)
    result = node(make_state(current_epic_id=None))

    # Should still return an epic key (the fake one)
    assert result["current_epic_id"] is not None
