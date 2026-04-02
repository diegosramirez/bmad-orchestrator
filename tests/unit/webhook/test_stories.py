"""Tests for stories_breakdown workflow input builder."""
from __future__ import annotations

from bmad_orchestrator.webhook.stories import build_stories_workflow_inputs


def test_build_stories_workflow_inputs() -> None:
    inputs = build_stories_workflow_inputs(
        issue_key="SAM1-275",
        target_repo="owner/app",
        team_id="SAM1",
    )
    assert inputs["prompt"] == "SAM1-275"
    assert inputs["target_repo"] == "owner/app"
    assert inputs["team_id"] == "SAM1"
    assert inputs["execution_mode"] == "stories_breakdown"
    assert inputs["skip_check_epic_state"] == "true"
    assert inputs["skip_create_or_correct_epic"] == "true"
    assert inputs["skip_create_story_tasks"] == "false"
    assert inputs["skip_party_mode_refinement"] == "false"
    assert inputs["skip_detect_commands"] == "true"
    assert inputs["skip_dev_story"] == "true"
    assert inputs["skip_epic_architect"] == "true"
    assert inputs["extra_flags"] == "--epic-key SAM1-275"
