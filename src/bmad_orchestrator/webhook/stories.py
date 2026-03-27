"""Workflow dispatch inputs for Forge-initiated epic story breakdown (N stories + party)."""
from __future__ import annotations

from bmad_orchestrator.webhook.discovery import team_id_from_issue_key

__all__ = ["build_stories_workflow_inputs", "team_id_from_issue_key"]


def build_stories_workflow_inputs(
    *,
    issue_key: str,
    target_repo: str,
    team_id: str,
) -> dict[str, str]:
    """Workflow inputs for stories_breakdown (create_story_tasks + party, then graph END).

    Skips epic prep nodes; runs create_story_tasks and party_mode_refinement.
    """
    extra_flags = f"--epic-key {issue_key} --story-key {issue_key}"
    return {
        "target_repo": target_repo,
        "base_branch": "main",
        "prompt": issue_key,
        "team_id": team_id,
        "run_id": "",
        "skip_check_epic_state": "true",
        "skip_create_or_correct_epic": "true",
        "skip_create_story_tasks": "false",
        "skip_party_mode_refinement": "false",
        "skip_detect_commands": "true",
        "skip_dev_story": "true",
        "skip_qa_automation": "true",
        "skip_code_review": "true",
        "skip_e2e_automation": "true",
        "skip_commit_and_push": "true",
        "skip_create_pull_request": "true",
        "skip_epic_architect": "true",
        "slack_verbose": "false",
        "slack_thread_ts": "",
        "branch": "",
        "extra_flags": extra_flags,
        "guidance": "",
        "execution_mode": "stories_breakdown",
        "auto_execute_issue": "false",
        "code_agent": "",
    }
