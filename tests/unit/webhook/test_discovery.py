"""Tests for Discovery workflow input builder."""
from __future__ import annotations

from bmad_orchestrator.webhook.discovery import (
    build_discovery_workflow_inputs,
    team_id_from_issue_key,
)


def test_team_id_from_issue_key() -> None:
    assert team_id_from_issue_key("SAM1-275", default_team_id="X") == "SAM1"
    assert team_id_from_issue_key("PUG-1", default_team_id="X") == "PUG"


def test_team_id_from_issue_key_fallback() -> None:
    assert team_id_from_issue_key("nodash", default_team_id="FALLBACK") == "FALLBACK"


def test_build_discovery_workflow_inputs_epic_only_path() -> None:
    inputs = build_discovery_workflow_inputs(
        issue_key="SAM1-275",
        target_repo="owner/app",
        team_id="SAM1",
    )
    assert inputs["prompt"] == "SAM1-275"
    assert inputs["target_repo"] == "owner/app"
    assert inputs["team_id"] == "SAM1"
    assert inputs["execution_mode"] == "discovery"
    assert inputs["skip_check_epic_state"] == "false"
    assert inputs["skip_create_or_correct_epic"] == "false"
    assert inputs["skip_create_story_tasks"] == "true"
    assert inputs["skip_party_mode_refinement"] == "true"
    assert inputs["skip_detect_commands"] == "true"
    assert inputs["skip_dev_story"] == "true"
    assert inputs["skip_qa_automation"] == "true"
    assert inputs["skip_code_review"] == "true"
    assert inputs["skip_e2e_automation"] == "true"
    assert inputs["skip_commit_and_push"] == "true"
    assert inputs["skip_create_pull_request"] == "true"
    assert "skip_create_github_issue" not in inputs
    assert "--epic-key SAM1-275 --story-key SAM1-275" in inputs["extra_flags"]
