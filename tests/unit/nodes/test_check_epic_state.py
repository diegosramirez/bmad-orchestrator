from __future__ import annotations

from bmad_orchestrator.nodes.check_epic_state import (
    EpicRoutingDecision,
    make_check_epic_state_node,
)
from tests.conftest import make_state


def test_returns_none_when_no_epics(settings, mock_jira, mock_claude):
    mock_jira.find_epic_by_team.return_value = []
    node = make_check_epic_state_node(mock_jira, mock_claude, settings)
    result = node(make_state())

    assert result["current_epic_id"] is None
    assert len(result["execution_log"]) == 1
    mock_claude.complete_structured.assert_not_called()


def test_returns_epic_when_decision_is_add_to_existing(settings, mock_jira, mock_claude):
    mock_jira.find_epic_by_team.return_value = [
        {"key": "TEST-1", "summary": "Auth Epic", "description": ""}
    ]
    mock_claude.complete_structured.return_value = EpicRoutingDecision(
        decision="add_to_existing", reason="Fits auth epic"
    )
    node = make_check_epic_state_node(mock_jira, mock_claude, settings)
    result = node(make_state())

    assert result["current_epic_id"] == "TEST-1"
    assert result["epic_routing_reason"] == "Fits auth epic"
    assert len(result["execution_log"]) == 1


def test_returns_none_when_decision_is_create_new(settings, mock_jira, mock_claude):
    mock_jira.find_epic_by_team.return_value = [
        {"key": "TEST-1", "summary": "Unrelated Epic", "description": ""}
    ]
    mock_claude.complete_structured.return_value = EpicRoutingDecision(
        decision="create_new", reason="Different scope"
    )
    node = make_check_epic_state_node(mock_jira, mock_claude, settings)
    result = node(make_state())

    assert result["current_epic_id"] is None
    assert result["epic_routing_reason"] == "Different scope"


def test_logs_team_id_in_message(settings, mock_jira, mock_claude):
    mock_jira.find_epic_by_team.return_value = []
    node = make_check_epic_state_node(mock_jira, mock_claude, settings)
    result = node(make_state(team_id="growth"))
    assert "growth" in result["execution_log"][0]["message"]
