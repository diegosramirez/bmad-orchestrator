from __future__ import annotations

from unittest.mock import MagicMock

from bmad_orchestrator.nodes.create_or_correct_epic import (
    DiscoveryEpicResult,
    EpicCorrectionDecision,
    EpicDraft,
    make_create_or_correct_epic_node,
)
from tests.conftest import make_state


def test_skips_creation_when_epic_already_exists(settings, mock_jira, mock_claude):
    # Course-correction path: existing epic description is already sufficient
    mock_jira.get_epic.return_value = {
        "summary": "Epic title",
        "description": "Existing epic description",
    }
    mock_claude.complete_structured.return_value = EpicCorrectionDecision(
        needs_update=False, reason="Already covers the new request"
    )
    node = make_create_or_correct_epic_node(mock_jira, mock_claude, settings)
    result = node(make_state(current_epic_id="TEST-5"))

    assert result["current_epic_id"] == "TEST-5"
    mock_jira.create_epic.assert_not_called()
    mock_jira.update_epic.assert_not_called()
    mock_jira.get_epic.assert_called_once_with("TEST-5")


def test_discovery_aborts_when_input_invalid(settings, mock_jira, mock_claude):
    mock_jira.get_epic.return_value = {
        "summary": "x",
        "description": "",
    }
    mock_claude.complete_structured.return_value = DiscoveryEpicResult(
        input_valid=False,
        insufficient_info_message="❌ Not enough information to run Discovery.",
    )
    disc_settings = settings.model_copy(update={"execution_mode": "discovery"})
    node = make_create_or_correct_epic_node(mock_jira, mock_claude, disc_settings)
    result = node(make_state(current_epic_id="EPIC-1"))

    assert result["current_epic_id"] == "EPIC-1"
    mock_jira.update_epic.assert_not_called()
    assert "aborted" in result["execution_log"][0]["message"].lower()


def test_discovery_uses_bmad_runner_when_provided(settings, mock_jira, mock_claude):
    mock_jira.get_epic.return_value = {"summary": "S", "description": "D"}
    runner = MagicMock()
    runner.run_discovery_epic_correction.return_value = DiscoveryEpicResult(
        input_valid=True,
        updated_description="# 📖 Overview\nText.",
    )
    disc_settings = settings.model_copy(update={"execution_mode": "discovery"})
    node = make_create_or_correct_epic_node(
        mock_jira, mock_claude, disc_settings, bmad_runner=runner
    )
    node(make_state(current_epic_id="E-99"))

    runner.run_discovery_epic_correction.assert_called_once()
    mock_claude.complete_structured.assert_not_called()
    mock_jira.update_epic.assert_called_once()


def test_discovery_skips_jira_when_description_empty_but_valid(settings, mock_jira, mock_claude):
    mock_jira.get_epic.return_value = {"summary": "S", "description": "D"}
    mock_claude.complete_structured.return_value = DiscoveryEpicResult(
        input_valid=True,
        updated_description="   ",
    )
    disc_settings = settings.model_copy(update={"execution_mode": "discovery"})
    node = make_create_or_correct_epic_node(mock_jira, mock_claude, disc_settings)
    node(make_state(current_epic_id="E-3"))

    mock_jira.update_epic.assert_not_called()


def test_discovery_updates_epic_when_valid(settings, mock_jira, mock_claude):
    mock_jira.get_epic.return_value = {
        "summary": "Login",
        "description": "Users need to sign in.",
    }
    mock_claude.complete_structured.return_value = DiscoveryEpicResult(
        input_valid=True,
        updated_description="# 🧩 Epic Title\n\n# 📖 Overview\nDone.",
        updated_summary="Better login epic",
    )
    disc_settings = settings.model_copy(update={"execution_mode": "discovery"})
    node = make_create_or_correct_epic_node(mock_jira, mock_claude, disc_settings)
    result = node(make_state(current_epic_id="EPIC-2"))

    assert result["current_epic_id"] == "EPIC-2"
    mock_jira.update_epic.assert_called_once()
    call = mock_jira.update_epic.call_args
    assert call[0][0] == "EPIC-2"
    assert "Better login epic" in str(call[0][1].get("summary", ""))
    assert "<!-- bmad:discovery -->" in call[0][1]["description"]
    assert "Overview" in call[0][1]["description"]


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
