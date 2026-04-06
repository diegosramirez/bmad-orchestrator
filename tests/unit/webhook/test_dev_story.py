"""Tests for Forge-initiated Story dev workflow input builder."""
from __future__ import annotations

from bmad_orchestrator.webhook.dev_story import build_dev_story_workflow_inputs


def test_build_dev_story_workflow_inputs() -> None:
    inputs = build_dev_story_workflow_inputs(
        issue_key="SAM1-275",
        target_repo="owner/app",
        team_id="SAM1",
    )
    assert inputs["prompt"] == "SAM1-275"
    assert inputs["target_repo"] == "owner/app"
    assert inputs["team_id"] == "SAM1"
    assert inputs["execution_mode"] == "inline"
    assert inputs["extra_flags"] == ""
    assert inputs["skip_check_epic_state"] == "true"
    assert inputs["skip_create_or_correct_epic"] == "true"
    assert inputs["skip_epic_architect"] == "true"
    assert inputs["skip_create_story_tasks"] == "true"
    assert inputs["skip_party_mode_refinement"] == "true"
    assert inputs["skip_detect_commands"] == "false"
    assert inputs["skip_dev_story"] == "false"
    assert inputs["skip_qa_automation"] == "false"
    assert inputs["skip_code_review"] == "false"
    assert inputs["skip_e2e_automation"] == "false"
    assert inputs["skip_commit_and_push"] == "false"
    assert inputs["skip_create_pull_request"] == "false"
