from __future__ import annotations

from unittest.mock import MagicMock, patch

from bmad_orchestrator.utils.cli_prompts import (
    confirm_action,
    confirm_epic,
    is_jira_key,
    select_epic_from_list,
    select_skip_nodes,
)

# ── is_jira_key ──────────────────────────────────────────────────────────────


def test_is_jira_key_valid():
    assert is_jira_key("PUG-437") is True
    assert is_jira_key("ABC-1") is True
    assert is_jira_key("AB12-999") is True


def test_is_jira_key_invalid():
    assert is_jira_key("pug-437") is False  # lowercase
    assert is_jira_key("PUG437") is False  # no dash
    assert is_jira_key("PUG-") is False  # no digits
    assert is_jira_key("A-1") is False  # single letter
    assert is_jira_key("") is False
    assert is_jira_key("Add SSO login") is False
    assert is_jira_key("123-ABC") is False  # starts with digits


# ── select_epic_from_list ─────────────────────────────────────────────────────

_EPICS = [
    {"key": "PUG-1", "summary": "Epic one", "status": "Open"},
    {"key": "PUG-2", "summary": "Epic two", "status": "In Progress"},
]


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_select_epic_returns_chosen(mock_q):
    mock_q.Choice = MagicMock(side_effect=lambda **kw: kw)
    mock_q.select.return_value.ask.return_value = "PUG-1"
    result = select_epic_from_list(_EPICS)
    assert result is not None
    assert result["key"] == "PUG-1"


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_select_epic_returns_second(mock_q):
    mock_q.Choice = MagicMock(side_effect=lambda **kw: kw)
    mock_q.select.return_value.ask.return_value = "PUG-2"
    result = select_epic_from_list(_EPICS)
    assert result is not None
    assert result["key"] == "PUG-2"


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_select_epic_returns_none_for_create_new(mock_q):
    mock_q.Choice = MagicMock(side_effect=lambda **kw: kw)
    mock_q.select.return_value.ask.return_value = "__create_new__"
    result = select_epic_from_list(_EPICS)
    assert result is None


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_select_epic_returns_none_on_ctrl_c(mock_q):
    mock_q.Choice = MagicMock(side_effect=lambda **kw: kw)
    mock_q.select.return_value.ask.return_value = None
    result = select_epic_from_list(_EPICS)
    assert result is None


# ── confirm_epic ──────────────────────────────────────────────────────────────

_EPIC = {"key": "PUG-1", "summary": "Test", "status": "Open", "description": "Desc"}


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_confirm_epic_yes(mock_q):
    mock_q.confirm.return_value.ask.return_value = True
    assert confirm_epic(_EPIC) is True


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_confirm_epic_no(mock_q):
    mock_q.confirm.return_value.ask.return_value = False
    assert confirm_epic(_EPIC) is False


# ── confirm_action ────────────────────────────────────────────────────────────


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_confirm_action_yes(mock_q):
    mock_q.confirm.return_value.ask.return_value = True
    assert confirm_action("Do something") is True


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_confirm_action_no(mock_q):
    mock_q.confirm.return_value.ask.return_value = False
    assert confirm_action("Do something") is False


# ── select_skip_nodes ────────────────────────────────────────────────────────


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_select_skip_nodes_returns_selected(mock_q):
    mock_q.Choice = MagicMock(side_effect=lambda **kw: kw)
    mock_q.checkbox.return_value.ask.return_value = ["qa_automation", "code_review"]
    result = select_skip_nodes()
    assert result == ["qa_automation", "code_review"]


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_select_skip_nodes_returns_empty_when_none_selected(mock_q):
    mock_q.Choice = MagicMock(side_effect=lambda **kw: kw)
    mock_q.checkbox.return_value.ask.return_value = []
    result = select_skip_nodes()
    assert result == []


@patch("bmad_orchestrator.utils.cli_prompts.questionary")
def test_select_skip_nodes_returns_empty_on_ctrl_c(mock_q):
    mock_q.Choice = MagicMock(side_effect=lambda **kw: kw)
    mock_q.checkbox.return_value.ask.return_value = None
    result = select_skip_nodes()
    assert result == []
