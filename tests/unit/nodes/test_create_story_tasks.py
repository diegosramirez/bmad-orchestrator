from __future__ import annotations

import json

from bmad_orchestrator.nodes.create_story_tasks import (
    ContractPlannedStory,
    EpicStoryBreakdown,
    ImplementationPlannedStory,
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

    node = make_create_story_tasks_node(mock_jira, mock_claude, settings)
    result = node(make_state(current_epic_id="TEST-1"))

    assert result["current_story_id"] == "TEST-10"
    assert result["acceptance_criteria"] == [
        "Can log in with valid creds",
        "Cannot log in with wrong creds",
    ]
    assert mock_jira.set_story_checklist_text.call_count == 1
    checklist_md = mock_jira.set_story_checklist_text.call_args[0][1]
    assert "Create login endpoint" in checklist_md
    assert "Write login tests" in checklist_md


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
            ImplementationPlannedStory(
                role="frontend",
                summary="As a user I want feature alpha so that I succeed",
                description="**Hypothesis**\nH1\n\n**Intervention**\nI1",
                acceptance_criteria=["AC a1", "AC a2"],
                tasks=[],
            ),
            ImplementationPlannedStory(
                role="backend",
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
    assert mock_jira.set_story_checklist_text.call_count == 1
    assert "Sub 1" in mock_jira.set_story_checklist_text.call_args[0][1]


def test_stories_breakdown_prompt_three_layer_pattern(settings, mock_jira, mock_claude):
    """user_message defaults to THREE stories: contracts, frontend, backend."""
    sb = settings.model_copy(update={"execution_mode": "stories_breakdown"})
    mock_jira.get_epic.return_value = _epic_with_discovery()
    mock_jira.list_stories_under_epic.return_value = []
    breakdown = EpicStoryBreakdown(
        stories=[
            ImplementationPlannedStory(
                role="frontend",
                summary="As a dev I want API contracts so that FE and BE align",
                description="**Hypothesis**\nH\n\n**Intervention**\nI",
                acceptance_criteria=["AC 1", "AC 2"],
                tasks=[],
            ),
        ]
    )
    mock_claude.complete_structured.return_value = breakdown
    mock_jira.create_story.return_value = {
        "key": "TEST-10",
        "summary": breakdown.stories[0].summary,
    }
    mock_jira.get_story.return_value = {
        "key": "TEST-10",
        "description": "**Acceptance Criteria:**\n- AC 1\n- AC 2\n",
    }

    node = make_create_story_tasks_node(mock_jira, mock_claude, sb)
    node(make_state(current_epic_id="TEST-1", team_id="growth"))

    assert mock_claude.complete_structured.call_count == 1
    user_message = mock_claude.complete_structured.call_args.kwargs["user_message"]
    assert "default to **THREE** stories" in user_message
    assert "contracts / interface" in user_message
    assert "Story B (**frontend**)" in user_message
    assert "Story C (**backend**)" in user_message
    assert "**Intervention**, **Mechanics**, and **Implementation Notes**" in user_message
    assert "src/app/" in user_message
    assert "Do **not** paste client file trees" in user_message
    assert '"role": "contract"' in user_message
    assert '"role": "frontend"' in user_message or '"role": "backend"' in user_message
    assert "Contract story (`role: contract`)" in user_message
    assert "full product-style Jira story template" in user_message


def test_stories_breakdown_prompt_template_note_applies_fe_be_only(
    settings,
    mock_jira,
    mock_claude,
    monkeypatch,
):
    """When Jira template is loaded, appendix says template applies to FE/BE only."""
    from bmad_orchestrator.nodes import create_story_tasks as cst

    def _mock_template(_app_root: object = None) -> str:
        return "# Mock template\n**Hypothesis**"

    monkeypatch.setattr(cst, "load_template", _mock_template)

    sb = settings.model_copy(update={"execution_mode": "stories_breakdown"})
    mock_jira.get_epic.return_value = _epic_with_discovery()
    mock_jira.list_stories_under_epic.return_value = []
    breakdown = EpicStoryBreakdown(
        stories=[
            ImplementationPlannedStory(
                role="backend",
                summary="As a dev I want one story so that it works",
                description="D",
                acceptance_criteria=["AC 1", "AC 2"],
                tasks=[],
            ),
        ],
    )
    mock_claude.complete_structured.return_value = breakdown
    mock_jira.create_story.return_value = {"key": "TEST-10", "summary": "S"}
    mock_jira.get_story.return_value = {"key": "TEST-10", "description": "X"}

    node = make_create_story_tasks_node(mock_jira, mock_claude, sb)
    node(make_state(current_epic_id="TEST-1", team_id="growth"))

    user_message = mock_claude.complete_structured.call_args.kwargs["user_message"]
    assert "**Frontend and backend stories" in user_message
    assert "Mock template" in user_message
    assert "apply to **frontend**" in user_message


def test_stories_breakdown_contract_skips_checklist_impl_keeps_checklist(
    settings,
    mock_jira,
    mock_claude,
):
    """Contract story never gets Checklist Text; frontend/backend still can."""
    sb = settings.model_copy(update={"execution_mode": "stories_breakdown"})
    mock_jira.get_epic.return_value = _epic_with_discovery()
    mock_jira.list_stories_under_epic.return_value = []
    breakdown = EpicStoryBreakdown(
        stories=[
            ContractPlannedStory(
                role="contract",
                summary="As a dev I want a shared API spec so that FE and BE align",
                description="**Hypothesis**\nDefine OpenAPI.\n\n**Intervention**\nPR to docs.",
                acceptance_criteria=["Spec merged", "Review approved"],
                spec_kind="OpenAPI 3.1",
                interface_deliverables=["docs/api/openapi.yaml"],
                error_and_auth_expectations="401/403 JSON body per spec",
                example_fixtures_scope="examples/*.json for happy path",
                out_of_scope_explicit=[
                    "No SPA or UI components",
                    "No server HTTP handlers or DB migrations",
                ],
            ),
            ImplementationPlannedStory(
                role="backend",
                summary="As a dev I want the API implemented so that clients work",
                description="**Hypothesis**\nH\n\n**Intervention**\nI",
                acceptance_criteria=["AC 1", "AC 2"],
                tasks=[
                    TaskItem(summary="Add handler", description="POST /widgets"),
                ],
            ),
        ]
    )
    mock_claude.complete_structured.return_value = breakdown
    mock_jira.create_story.side_effect = [
        {"key": "TEST-10", "summary": breakdown.stories[0].summary},
        {"key": "TEST-11", "summary": breakdown.stories[1].summary},
    ]
    mock_jira.get_story.return_value = {
        "key": "TEST-11",
        "description": "**Acceptance Criteria:**\n- AC 1\n- AC 2\n",
    }

    node = make_create_story_tasks_node(mock_jira, mock_claude, sb)
    node(make_state(current_epic_id="TEST-1", team_id="growth"))

    assert mock_jira.set_story_checklist_text.call_count == 1
    checklist_key = mock_jira.set_story_checklist_text.call_args[0][0]
    assert checklist_key == "TEST-11"

    first_desc = mock_jira.create_story.call_args_list[0].kwargs["description"]
    assert "**Spec kind**" in first_desc
    assert "**Interface deliverables**" in first_desc
    assert "openapi.yaml" in first_desc


def test_stories_breakdown_passes_epic_customfield_to_stories(settings, mock_jira, mock_claude):
    sb = settings.model_copy(
        update={
            "execution_mode": "stories_breakdown",
            "jira_target_repo_custom_field_id": "customfield_10112",
        },
    )
    mock_jira.get_epic.return_value = _epic_with_discovery()
    mock_jira.list_stories_under_epic.return_value = []
    mock_jira.get_epic_customfield_10112_value.return_value = {"value": "shared-repo"}
    breakdown = EpicStoryBreakdown(
        stories=[
            ImplementationPlannedStory(
                role="backend",
                summary="As a user I want one story so that it works",
                description="**Hypothesis**\nH\n\n**Intervention**\nI",
                acceptance_criteria=["AC 1", "AC 2"],
                tasks=[],
            ),
        ]
    )
    mock_claude.complete_structured.return_value = breakdown
    mock_jira.create_story.return_value = {
        "key": "TEST-10",
        "summary": breakdown.stories[0].summary,
    }
    mock_jira.get_story.return_value = {
        "key": "TEST-10",
        "description": "**Acceptance Criteria:**\n- AC 1\n- AC 2\n",
    }

    node = make_create_story_tasks_node(mock_jira, mock_claude, sb)
    node(make_state(current_epic_id="TEST-1", team_id="growth"))

    assert mock_jira.create_story.call_count == 1
    _args, kwargs = mock_jira.create_story.call_args
    assert kwargs.get("extra_fields") == {"customfield_10112": {"value": "shared-repo"}}


def test_stories_breakdown_skips_duplicate_against_existing(settings, mock_jira, mock_claude):
    sb = settings.model_copy(update={"execution_mode": "stories_breakdown"})
    mock_jira.get_epic.return_value = _epic_with_discovery()
    mock_jira.list_stories_under_epic.return_value = [
        {"summary": "As a user I want feature alpha so that I succeed", "key": "TEST-99"},
    ]
    breakdown = EpicStoryBreakdown(
        stories=[
            ImplementationPlannedStory(
                role="frontend",
                summary="As a user I want feature alpha so that I succeed",
                description="Dup",
                acceptance_criteria=["AC 1", "AC 2"],
                tasks=[],
            ),
            ImplementationPlannedStory(
                role="backend",
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
