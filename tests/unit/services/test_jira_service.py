from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bmad_orchestrator.services.jira_service import JiraService, _issue_to_dict
from bmad_orchestrator.utils.jira_adf import description_for_jira_api


def _make_mock_issue(
    key: str = "TEST-1",
    summary: str = "Test Issue",
    description: str = "Desc",
    status_name: str = "Open",
    issuetype_name: str = "Story",
    labels: list | None = None,
    parent_key: str | None = None,
) -> MagicMock:
    issue = MagicMock()
    issue.key = key
    issue.id = f"id-{key}"
    issue.fields.summary = summary
    issue.fields.description = description
    issue.fields.status.name = status_name
    issue.fields.issuetype.name = issuetype_name
    issue.fields.labels = labels or []
    if parent_key:
        issue.fields.parent.key = parent_key
    else:
        issue.fields.parent = None
    return issue


@pytest.fixture
def jira_svc(settings):
    """JiraService backed by a mocked JIRA client with dry_run=False."""
    with patch("bmad_orchestrator.services.jira_service.JIRA") as MockJIRA:
        mock_client = MagicMock()
        MockJIRA.return_value = mock_client
        non_dry = settings.model_copy(update={"dry_run": False})
        svc = JiraService(non_dry)
        _ = svc._client  # trigger cached_property → covers line 39
        yield svc, mock_client


# ── _issue_to_dict ────────────────────────────────────────────────────────────

def test_issue_to_dict_maps_all_fields():
    issue = _make_mock_issue(key="PUG-1", summary="Epic", description="Desc", labels=["pug"])
    result = _issue_to_dict(issue)
    assert result["key"] == "PUG-1"
    assert result["summary"] == "Epic"
    assert result["description"] == "Desc"
    assert result["status"] == "Open"
    assert result["issue_type"] == "Story"
    assert result["labels"] == ["pug"]
    assert result["parent_key"] is None


def test_issue_to_dict_includes_parent_key():
    issue = _make_mock_issue(key="PUG-5", parent_key="PUG-1")
    result = _issue_to_dict(issue)
    assert result["parent_key"] == "PUG-1"


def test_issue_to_dict_converts_adf_description_to_markdown():
    issue = _make_mock_issue()
    issue.fields.description = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "From ADF"}]},
        ],
    }
    result = _issue_to_dict(issue)
    assert result["description"] == "From ADF"


# ── find_epic_by_team ─────────────────────────────────────────────────────────

def test_find_epic_by_team_returns_list(jira_svc):
    svc, client = jira_svc
    client.search_issues.return_value = [_make_mock_issue(key="PUG-10")]
    result = svc.find_epic_by_team("pug")
    assert len(result) == 1
    assert result[0]["key"] == "PUG-10"
    client.search_issues.assert_called_once()


def test_find_epic_by_team_empty(jira_svc):
    svc, client = jira_svc
    client.search_issues.return_value = []
    assert svc.find_epic_by_team("pug") == []


# ── get_epic ─────────────────────────────────────────────────────────────────

def test_get_epic_returns_epic_dict(jira_svc):
    svc, client = jira_svc
    client.issue.return_value = _make_mock_issue(
        key="PUG-437", summary="BMAD Orchestrator", issuetype_name="Epic"
    )
    result = svc.get_epic("PUG-437")
    assert result is not None
    assert result["key"] == "PUG-437"
    assert result["issue_type"] == "Epic"
    client.issue.assert_called_once_with("PUG-437")


def test_get_epic_returns_none_for_non_epic(jira_svc):
    svc, client = jira_svc
    client.issue.return_value = _make_mock_issue(
        key="PUG-10", issuetype_name="Story"
    )
    result = svc.get_epic("PUG-10")
    assert result is None


def test_get_epic_returns_none_on_exception(jira_svc):
    svc, client = jira_svc
    client.issue.side_effect = Exception("Not found")
    result = svc.get_epic("MISSING-1")
    assert result is None


# ── create_epic ───────────────────────────────────────────────────────────────

def test_create_epic_calls_jira(jira_svc):
    svc, client = jira_svc
    client.create_issue.return_value = _make_mock_issue(key="PUG-99", summary="New Epic")
    result = svc.create_epic("New Epic", "Some desc", "pug")
    assert result["key"] == "PUG-99"
    client.create_issue.assert_called_once()


def test_create_epic_dry_run_skips(settings):
    dry = settings.model_copy(update={"dry_run": True})
    result = JiraService(dry).create_epic("Epic", "Desc", "pug")
    assert result["key"] == "DRY-001"


# ── update_epic ───────────────────────────────────────────────────────────────

def test_update_epic_calls_jira(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue(key="PUG-5")
    client.issue.return_value = issue
    result = svc.update_epic("PUG-5", {"description": "New"})
    assert result["key"] == "PUG-5"
    issue.update.assert_called_once()


# ── create_story ──────────────────────────────────────────────────────────────

def test_create_story_calls_jira(jira_svc):
    svc, client = jira_svc
    client.create_issue.return_value = _make_mock_issue(key="PUG-20", summary="Story")
    result = svc.create_story("PUG-10", "Story", "Desc", ["AC1", "AC2"], "pug")
    assert result["key"] == "PUG-20"
    client.create_issue.assert_called_once()


# ── create_task ───────────────────────────────────────────────────────────────

def test_create_task_calls_jira(jira_svc):
    svc, client = jira_svc
    client.create_issue.return_value = _make_mock_issue(key="PUG-30", summary="Task")
    result = svc.create_task("PUG-20", "Task", "Desc")
    assert result["key"] == "PUG-30"
    client.create_issue.assert_called_once()


# ── get_story ─────────────────────────────────────────────────────────────────

def test_get_story_returns_dict(jira_svc):
    svc, client = jira_svc
    client.issue.return_value = _make_mock_issue(key="PUG-5")
    result = svc.get_story("PUG-5")
    assert result is not None
    assert result["key"] == "PUG-5"


def test_get_story_returns_none_on_error(jira_svc):
    svc, client = jira_svc
    client.issue.side_effect = Exception("Not found")
    assert svc.get_story("MISSING-1") is None


# ── update_story_description ──────────────────────────────────────────────────

def test_update_story_description(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue()
    client.issue.return_value = issue
    svc.update_story_description("PUG-5", "New description")
    issue.update.assert_called_once_with(
        fields={"description": description_for_jira_api("New description")},
    )


def test_update_story_summary(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue()
    client.issue.return_value = issue
    svc.update_story_summary("PUG-5", "New summary")
    issue.update.assert_called_once_with(fields={"summary": "New summary"})


def test_set_story_branch_field(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue()
    client.issue.return_value = issue
    svc.set_story_branch_field("SAM1-61", "bmad/sam1/SAM1-61-add-signup")
    issue.update.assert_called_once_with(
        fields={"customfield_10145": "bmad/sam1/SAM1-61-add-signup"},
    )


# ── get_subtasks ───────────────────────────────────────────────────────────────


def test_get_subtasks_returns_mapped_list(jira_svc):
    svc, client = jira_svc
    client.search_issues.return_value = [
        _make_mock_issue(key="PUG-21", summary="Subtask 1", issuetype_name="Subtask"),
        _make_mock_issue(key="PUG-22", summary="Subtask 2", issuetype_name="Subtask"),
    ]
    result = svc.get_subtasks("PUG-20")
    assert [r["key"] for r in result] == ["PUG-21", "PUG-22"]
    client.search_issues.assert_called_once()


def test_get_subtasks_returns_empty_on_exception(jira_svc):
    svc, client = jira_svc
    client.search_issues.side_effect = Exception("boom")
    assert svc.get_subtasks("PUG-20") == []


# ── transition_issue ──────────────────────────────────────────────────────────

def test_transition_issue_found(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue()
    client.issue.return_value = issue
    client.transitions.return_value = [{"name": "Done", "id": "31"}]
    svc.transition_issue("PUG-5", "done")
    client.transition_issue.assert_called_once_with(issue, "31")


def test_transition_issue_not_found_does_not_transition(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue()
    client.issue.return_value = issue
    client.transitions.return_value = [{"name": "Open", "id": "11"}]
    svc.transition_issue("PUG-5", "nonexistent")
    client.transition_issue.assert_not_called()
