"""Tests for Epic Architect workflow input builder."""
from __future__ import annotations

from bmad_orchestrator.webhook.epic_architect import build_epic_architect_workflow_inputs


def test_build_epic_architect_workflow_inputs_skips_all_but_epic_architect() -> None:
    inputs = build_epic_architect_workflow_inputs(
        issue_key="SAM1-300",
        target_repo="owner/app",
        team_id="SAM1",
    )
    assert inputs["prompt"] == "SAM1-300"
    assert inputs["target_repo"] == "owner/app"
    assert inputs["team_id"] == "SAM1"
    assert inputs["execution_mode"] == "epic_architect"
    assert inputs["skip_check_epic_state"] == "true"
    assert inputs["skip_create_or_correct_epic"] == "true"
    assert inputs["skip_create_story_tasks"] == "true"
    assert inputs["skip_party_mode_refinement"] == "true"
    assert inputs["skip_detect_commands"] == "true"
    assert inputs["skip_dev_story"] == "true"
    assert inputs["skip_epic_architect"] == "false"
    assert "--epic-key SAM1-300 --story-key SAM1-300" in inputs["extra_flags"]
