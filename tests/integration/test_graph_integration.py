"""
Integration test: runs the full LangGraph graph with all services mocked.
Uses MemorySaver (no SQLite file) so tests are fast and side-effect-free.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.graph import build_graph, make_initial_state
from bmad_orchestrator.nodes.code_review import ReviewIssueItem, ReviewResult
from bmad_orchestrator.nodes.create_or_correct_epic import EpicDraft
from bmad_orchestrator.nodes.create_story_tasks import StoryDraft, TaskItem
from bmad_orchestrator.nodes.dev_story import (
    ChecklistCompletionAssessment,
    FileOperationList,
    FilePlan,
)
from bmad_orchestrator.nodes.party_mode_refinement import (
    RefinedStory,
    _SubtaskItem,
    _SubtaskList,
)
from bmad_orchestrator.services.claude_agent_service import AgentResult


@pytest.fixture
def dry_settings() -> Settings:
    return Settings(
        anthropic_api_key="test",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        dry_run=True,
        max_review_loops=2,
        checkpoint_db_path=":memory:",
    )


def _configure_mocks(
    mock_jira: MagicMock,
    mock_claude: MagicMock,
    mock_agent: MagicMock,
    mock_git: MagicMock,
    mock_github: MagicMock,
) -> None:
    # Jira service mocks
    mock_jira.find_epic_by_team.return_value = []
    mock_jira.create_epic.return_value = {"key": "TEST-1", "summary": "Test Epic"}
    mock_jira.create_story.return_value = {"key": "TEST-2", "summary": "Test Story"}
    mock_jira.get_story.return_value = None
    mock_jira.update_story_description.return_value = None
    mock_jira.story_checklist_text_is_empty.return_value = False
    mock_jira.get_story_checklist_text.return_value = ""

    # Claude service mocks (used for structured-data nodes)
    mock_claude.classify.return_value = "create_new"
    mock_claude.complete.return_value = "AI output"
    mock_claude.complete_structured.side_effect = _structured_side_effect
    mock_claude._usage = []

    # Claude Agent SDK mocks (used for code-gen/review nodes)
    mock_agent.run_agent.return_value = AgentResult(
        touched_files=[],
        structured_output=ReviewResult(issues=[], overall_assessment="LGTM"),
    )

    # Git service mocks
    mock_git.get_current_branch.return_value = "main"
    mock_git.make_branch_name.return_value = "bmad/team-alpha/TEST-2-add-auth"
    mock_git.commit.return_value = "abc123"
    mock_git.push.return_value = None
    mock_git.create_and_checkout_branch.return_value = None
    mock_git.stage_path.return_value = None
    mock_git.stage_all.return_value = None
    mock_git.has_staged_changes.return_value = True
    mock_git.get_head_sha.return_value = "abc123"

    # GitHub service mocks
    mock_github.pr_exists.return_value = None
    mock_github.create_pr.return_value = "https://github.com/org/repo/pull/99"


def _structured_side_effect(  # type: ignore[return]
    system_prompt: str, user_message: str, schema: type, **_: object,
) -> object:
    """Return a valid minimal instance of the requested schema."""
    if schema.__name__ == "EpicDraft":
        return EpicDraft(summary="Test Epic", description="Test description")
    if schema.__name__ == "EpicCorrectionDecision":
        return schema(needs_update=False, updated_description="", reason="")
    if schema.__name__ == "StoryDraft":
        return StoryDraft(
            summary="As a user I want to log in",
            description="Implement auth",
            acceptance_criteria=["Can log in", "Cannot use wrong creds"],
            tasks=[
                TaskItem(summary="Create endpoint", description="POST /auth/login"),
                TaskItem(summary="Write tests", description="pytest"),
            ],
        )
    if schema.__name__ == "StoryQualityAssessment":
        return schema(is_clear=True, issues=[])
    if schema.__name__ == "FilePlan":
        return FilePlan(files=[])
    if schema.__name__ == "FileContent":
        return schema(content="")
    if schema.__name__ == "FileOperationList":
        return FileOperationList(operations=[])
    if schema.__name__ == "ReviewResult":
        return ReviewResult(issues=[], overall_assessment="LGTM")
    if schema.__name__ == "RefinedStory":
        return RefinedStory(
            updated_summary="As a user I want to log in",
            updated_description="Implement auth with party mode refinements",
            acceptance_criteria=["Can log in", "Cannot use wrong creds"],
            implementation_notes="Use JWT tokens",
        )
    if schema.__name__ == "_SubtaskList":
        return _SubtaskList(
            tasks=[
                _SubtaskItem(summary="Integration task 1", description="First"),
                _SubtaskItem(summary="Integration task 2", description="Second"),
            ],
        )
    if schema.__name__ == "ChecklistCompletionAssessment":
        return ChecklistCompletionAssessment(completed_task_summaries=[])
    return schema()


@pytest.fixture
def mock_services(dry_settings: Settings):
    mock_jira = MagicMock()
    mock_claude = MagicMock()
    mock_agent = MagicMock()
    mock_git = MagicMock()
    mock_github = MagicMock()
    _configure_mocks(mock_jira, mock_claude, mock_agent, mock_git, mock_github)
    return mock_jira, mock_claude, mock_agent, mock_git, mock_github


def test_full_graph_sunny_path_reaches_pr(dry_settings, mock_services):
    """Full graph completes and produces a PR URL."""
    mock_jira, mock_claude, mock_agent, mock_git, mock_github = mock_services

    with (
        patch("bmad_orchestrator.graph.create_jira_service", return_value=mock_jira),
        patch("bmad_orchestrator.graph.ClaudeService", return_value=mock_claude),
        patch("bmad_orchestrator.graph.ClaudeAgentService", return_value=mock_agent),
        patch("bmad_orchestrator.graph.GitService", return_value=mock_git),
        patch("bmad_orchestrator.graph.create_github_service", return_value=mock_github),
    ):
        graph, _, _ = build_graph(dry_settings)
        initial = make_initial_state("team-alpha", "Add user authentication")
        config = {"configurable": {"thread_id": "test-sunny-path"}}

        final = graph.invoke(initial, config=config)

    assert final["pr_url"] == "https://github.com/org/repo/pull/99"
    assert final["failure_state"] is None
    assert final["current_story_id"] == "TEST-2"


def test_review_loop_terminates_at_max(dry_settings, mock_services):
    """Code review loop stops after max_review_loops even with remaining issues."""
    mock_jira, mock_claude, mock_agent, mock_git, mock_github = mock_services

    # Agent returns critical-severity issues from code_review node.
    # Must be "critical" to block at all loop levels with progressive leniency.
    mock_agent.run_agent.return_value = AgentResult(
        touched_files=[],
        structured_output=ReviewResult(
            issues=[ReviewIssueItem(severity="critical", file="x.py", description="Bug")],
            overall_assessment="needs fixes",
        ),
    )

    with (
        patch("bmad_orchestrator.graph.create_jira_service", return_value=mock_jira),
        patch("bmad_orchestrator.graph.ClaudeService", return_value=mock_claude),
        patch("bmad_orchestrator.graph.ClaudeAgentService", return_value=mock_agent),
        patch("bmad_orchestrator.graph.GitService", return_value=mock_git),
        patch("bmad_orchestrator.graph.create_github_service", return_value=mock_github),
    ):
        graph, _, _ = build_graph(dry_settings)
        initial = make_initial_state("team-alpha", "Add auth")
        config = {"configurable": {"thread_id": "test-review-loop"}}

        final = graph.invoke(initial, config=config)

    # Should reach END via fail_with_state → commit → PR (draft) when max loops exceeded
    assert final["failure_state"] is not None
    assert (
        "max" in final["failure_state"].lower()
        or "loop" in final["failure_state"].lower()
        or "review" in final["failure_state"].lower()
    )
    # Pipeline creates a draft PR even on failure (with failure diagnostics)
    assert final["pr_url"] is not None
    assert final["review_loop_count"] == dry_settings.max_review_loops
