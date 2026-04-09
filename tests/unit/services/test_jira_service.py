from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bmad_orchestrator.services.jira_service import (
    JiraService,
    _is_transient,
    _issue_to_dict,
    _retry_jira,
)
from bmad_orchestrator.utils.jira_adf import (
    description_for_jira_api,
    paragraph_custom_field_payload_for_api,
)


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


def test_jira_client_uses_rest_api_v3_for_adf_descriptions(settings):
    """ADF issue descriptions require /rest/api/3; v2 expects a string and rejects dicts."""
    with patch("bmad_orchestrator.services.jira_service.JIRA") as MockJIRA:
        MockJIRA.return_value = MagicMock()
        non_dry = settings.model_copy(update={"dry_run": False})
        svc = JiraService(non_dry)
        _ = svc._client
        MockJIRA.assert_called_once()
        assert MockJIRA.call_args.kwargs["options"]["rest_api_version"] == "3"


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


def test_issue_to_dict_prefers_raw_json_description_over_property_holder():
    """Use issue.raw fields.description dict so we do not rely on python-jira PropertyHolder."""
    from jira.resources import dict2resource

    issue = MagicMock()
    issue.key = "TEST-275"
    issue.id = "11457"
    issue.fields.summary = "Epic title"
    adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "From raw JSON fields"}]},
        ],
    }
    issue.fields.description = dict2resource(adf)
    issue.fields.status.name = "Open"
    issue.fields.issuetype.name = "Epic"
    issue.fields.labels = []
    issue.fields.parent = None
    issue.raw = {"fields": {"description": adf}}

    result = _issue_to_dict(issue)
    assert result["description"] == "From raw JSON fields"


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


def test_create_epic_mermaid_pipeline_two_phase(jira_svc):
    """With mermaid renderer on: attach PNGs, description ADF with placeholder (no inline media)."""
    import base64

    svc, client = jira_svc
    svc.settings = svc.settings.model_copy(update={"mermaid_renderer": "kroki"})
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    )
    created = MagicMock()
    created.key = "PUG-99"
    created.update = MagicMock()
    client.create_issue.return_value = created
    client.add_attachment.return_value = MagicMock()
    with patch("bmad_orchestrator.utils.jira_mermaid.render_mermaid_to_png") as mock_render:
        mock_render.return_value = (png, None)
        svc.create_epic("E", "```mermaid\nflowchart LR\n  A-->B\n```", "pug")
    client.create_issue.assert_called_once()
    created.update.assert_called_once()
    final_desc = created.update.call_args.kwargs["fields"]["description"]
    assert final_desc["type"] == "doc"
    assert not any(
        b.get("type") == "mediaSingle" for b in final_desc.get("content", [])
    )
    assert "review it in the Attachments section" in str(final_desc)
    client.add_attachment.assert_called_once()


# ── update_epic ───────────────────────────────────────────────────────────────

def test_update_epic_calls_jira(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue(key="PUG-5")
    client.issue.return_value = issue
    result = svc.update_epic("PUG-5", {"description": "New"})
    assert result["key"] == "PUG-5"
    issue.update.assert_called_once()


def test_update_epic_mermaid_pipeline(jira_svc):
    import base64

    svc, client = jira_svc
    svc.settings = svc.settings.model_copy(update={"mermaid_renderer": "kroki"})
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    )
    issue = _make_mock_issue(key="PUG-5")
    client.issue.return_value = issue
    mock_att = MagicMock()
    mock_att.id = "att-9"
    client.add_attachment.return_value = mock_att
    with patch("bmad_orchestrator.utils.jira_mermaid.render_mermaid_to_png") as mock_render:
        mock_render.return_value = (png, None)
        svc.update_epic("PUG-5", {"description": "```mermaid\nflowchart LR\n  A-->B\n```"})
    issue.update.assert_called_once()
    call_kw = issue.update.call_args.kwargs["fields"]
    assert call_kw["description"]["type"] == "doc"


def test_update_story_description_mermaid(jira_svc):
    import base64

    svc, client = jira_svc
    svc.settings = svc.settings.model_copy(update={"mermaid_renderer": "kroki"})
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    )
    issue = _make_mock_issue()
    client.issue.return_value = issue
    mock_att = MagicMock()
    mock_att.id = "a1"
    client.add_attachment.return_value = mock_att
    with patch("bmad_orchestrator.utils.jira_mermaid.render_mermaid_to_png") as mock_render:
        mock_render.return_value = (png, None)
        svc.update_story_description("PUG-5", "```mermaid\nflowchart LR\n  A-->B\n```")
    issue.update.assert_called_once()
    assert issue.update.call_args.kwargs["fields"]["description"]["type"] == "doc"


# ── create_story ──────────────────────────────────────────────────────────────

def test_create_story_calls_jira(jira_svc):
    svc, client = jira_svc
    client.create_issue.return_value = _make_mock_issue(key="PUG-20", summary="Story")
    result = svc.create_story("PUG-10", "Story", "Desc", ["AC1", "AC2"], "pug")
    assert result["key"] == "PUG-20"
    client.create_issue.assert_called_once()


def test_create_story_merges_extra_fields(jira_svc):
    svc, client = jira_svc
    client.create_issue.return_value = _make_mock_issue(key="PUG-20", summary="Story")
    svc.create_story(
        "PUG-10",
        "Story",
        "Desc",
        ["AC1"],
        "pug",
        extra_fields={"customfield_10112": {"value": "my-app"}},
    )
    fields = client.create_issue.call_args.kwargs["fields"]
    assert fields["customfield_10112"] == {"value": "my-app"}


def test_get_epic_customfield_10112_value_reads_raw(jira_svc):
    svc, client = jira_svc
    fid = svc.settings.jira_target_repo_custom_field_id
    issue = _make_mock_issue(key="PUG-10", issuetype_name="Epic")
    issue.raw = {"fields": {fid: {"value": "slug-only"}}}
    client.issue.return_value = issue
    assert svc.get_epic_customfield_10112_value("PUG-10") == {"value": "slug-only"}


def test_get_epic_customfield_10112_value_non_epic_returns_none(jira_svc):
    svc, client = jira_svc
    issue = _make_mock_issue(issuetype_name="Story")
    issue.raw = {"fields": {"customfield_10112": {"value": "x"}}}
    client.issue.return_value = issue
    assert svc.get_epic_customfield_10112_value("PUG-5") is None


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

def test_add_comment_converts_body_to_adf(jira_svc):
    """REST API v3 requires ADF for comment body (same as issue description)."""
    svc, client = jira_svc
    mock_comment = MagicMock()
    mock_comment.id = "c42"
    client.add_comment.return_value = mock_comment
    result = svc.add_comment("PUG-5", "Hello **bold**")
    assert result == "c42"
    client.add_comment.assert_called_once_with(
        "PUG-5",
        description_for_jira_api("Hello **bold**"),
    )


def test_update_comment_converts_body_to_adf(jira_svc):
    svc, client = jira_svc
    mock_comment = MagicMock()
    client.comment.return_value = mock_comment
    svc.update_comment("PUG-5", "99", "Line one")
    mock_comment.update.assert_called_once_with(
        body=description_for_jira_api("Line one"),
    )


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
    fid = svc.settings.jira_branch_custom_field_id
    issue = _make_mock_issue()
    client.issue.return_value = issue
    svc.set_story_branch_field("SAM1-61", "bmad/sam1/SAM1-61-add-signup")
    issue.update.assert_called_once_with(
        fields={fid: "bmad/sam1/SAM1-61-add-signup"},
    )


def test_set_story_branch_field_respects_settings_field_id(jira_svc, settings):
    svc, client = jira_svc
    custom = settings.model_copy(
        update={
            "dry_run": False,
            "jira_branch_custom_field_id": "customfield_77777",
        },
    )
    svc = type(svc)(custom)
    issue = _make_mock_issue()
    client.issue.return_value = issue
    svc.set_story_branch_field("X-1", "feature/foo")
    issue.update.assert_called_once_with(
        fields={"customfield_77777": "feature/foo"},
    )


def test_story_checklist_text_is_empty(jira_svc):
    svc, client = jira_svc
    fid = svc.settings.jira_checklist_text_custom_field_id
    empty_issue = MagicMock()
    empty_issue.raw = {"fields": {fid: None}}
    filled_issue = MagicMock()
    filled_issue.raw = {"fields": {fid: "not empty"}}
    client.issue.side_effect = [empty_issue, filled_issue]
    assert svc.story_checklist_text_is_empty("PUG-1") is True
    assert svc.story_checklist_text_is_empty("PUG-2") is False


def test_story_checklist_text_is_empty_returns_true_on_fetch_error(jira_svc):
    svc, client = jira_svc
    client.issue.side_effect = RuntimeError("network")
    assert svc.story_checklist_text_is_empty("PUG-9") is True


def test_set_story_checklist_text(jira_svc):
    svc, client = jira_svc
    fid = svc.settings.jira_checklist_text_custom_field_id
    fetch_issue = MagicMock()
    fetch_issue.raw = {"fields": {fid: None}}
    update_issue = MagicMock()

    def _issue_side_effect(key: str, fields: str | None = None) -> MagicMock:
        return fetch_issue if fields else update_issue

    client.issue.side_effect = _issue_side_effect
    md = "* [ ] **A** — b"
    svc.set_story_checklist_text("PUG-5", md)
    payload = paragraph_custom_field_payload_for_api(None, md)
    update_issue.update.assert_called_once_with(fields={fid: payload})


# ── list_stories_under_epic ─────────────────────────────────────────────────────


def test_list_stories_under_epic_returns_mapped_list(jira_svc):
    svc, client = jira_svc
    client.search_issues.return_value = [
        _make_mock_issue(key="PUG-10", summary="S1"),
        _make_mock_issue(key="PUG-11", summary="S2"),
    ]
    result = svc.list_stories_under_epic("PUG-1")
    assert [r["key"] for r in result] == ["PUG-10", "PUG-11"]


def test_list_stories_under_epic_returns_empty_on_exception(jira_svc):
    svc, client = jira_svc
    client.search_issues.side_effect = RuntimeError("jql error")
    assert svc.list_stories_under_epic("PUG-1") == []


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


# ── _is_transient ─────────────────────────────────────────────────────────────


def test_is_transient_true_for_timeout():
    assert _is_transient(Exception("Connection timed out")) is True


def test_is_transient_true_for_502():
    assert _is_transient(Exception("502 Bad Gateway")) is True


def test_is_transient_true_for_rate_limit():
    assert _is_transient(Exception("429 rate limit")) is True


def test_is_transient_false_for_auth():
    assert _is_transient(Exception("401 Unauthorized")) is False


def test_is_transient_false_for_field_error():
    assert _is_transient(Exception("Field 'foo' is required")) is False


# ── _retry_jira ───────────────────────────────────────────────────────────────


def test_retry_jira_succeeds_first_try():
    assert _retry_jira(lambda: 42, label="test") == 42


def test_retry_jira_retries_transient_then_succeeds():
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise Exception("connection timed out")  # noqa: TRY002
        return "ok"

    result = _retry_jira(fn, label="test", delay=0)
    assert result == "ok"
    assert len(calls) == 2


def test_retry_jira_fails_fast_on_permanent():
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        raise Exception("401 Unauthorized")  # noqa: TRY002

    with pytest.raises(Exception, match="401"):
        _retry_jira(fn, label="test", delay=0)
    assert len(calls) == 1  # no retry


# ── find_epic_by_team resilience ──────────────────────────────────────────────


def test_find_epic_by_team_returns_empty_on_exception(jira_svc):
    svc, client = jira_svc
    client.search_issues.side_effect = Exception("API down")
    result = svc.find_epic_by_team("growth")
    assert result == []
