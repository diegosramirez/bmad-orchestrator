"""Unit tests for the update_jira_branch node."""
from __future__ import annotations

from bmad_orchestrator.nodes.update_jira_branch import make_update_jira_branch_node
from tests.conftest import make_state


def test_updates_jira_branch_field_when_story_and_branch_present(settings, mock_jira):
    node = make_update_jira_branch_node(mock_jira, settings)
    result = node(make_state(
        current_story_id="SAM1-61",
        branch_name="bmad/sam1/SAM1-61-add-signup",
    ))

    mock_jira.set_story_branch_field.assert_called_once_with(
        "SAM1-61",
        "bmad/sam1/SAM1-61-add-signup",
    )
    assert len(result["execution_log"]) == 1
    assert "customfield_10145" in result["execution_log"][0]["message"]


def test_skips_when_missing_story_key(settings, mock_jira):
    node = make_update_jira_branch_node(mock_jira, settings)
    result = node(make_state(branch_name="bmad/sam1/SAM1-61-add-signup"))

    mock_jira.set_story_branch_field.assert_not_called()
    assert len(result["execution_log"]) == 1
    assert "Missing" in result["execution_log"][0]["message"]


def test_skips_when_missing_branch_name(settings, mock_jira):
    node = make_update_jira_branch_node(mock_jira, settings)
    result = node(make_state(current_story_id="SAM1-61"))

    mock_jira.set_story_branch_field.assert_not_called()
    assert len(result["execution_log"]) == 1
    assert "Missing" in result["execution_log"][0]["message"]
