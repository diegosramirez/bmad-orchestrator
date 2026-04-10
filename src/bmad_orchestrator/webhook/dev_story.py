"""Workflow dispatch inputs for Forge-initiated Story development (detect → dev → QA → PR)."""
from __future__ import annotations

__all__ = ["build_dev_story_workflow_inputs"]


def build_dev_story_workflow_inputs(
    *,
    issue_key: str,
    target_repo: str,
    team_id: str,
) -> dict[str, str]:
    """Workflow inputs for a full dev pipeline on an existing Story.

    Skips epic validation, epic create/update, epic architect, story/task creation,
    party refinement, and E2E automation (Playwright). Runs detect_commands through
    create_pull_request (inline).
    """
    # prompt = story key: CLI treats Jira-shaped prompt as --story-key and loads story.
    return {
        "target_repo": target_repo,
        "base_branch": "main",
        "prompt": issue_key,
        "team_id": team_id,
        "run_id": "",
        "skip_check_epic_state": "true",
        "skip_create_or_correct_epic": "true",
        "skip_create_story_tasks": "true",
        "skip_party_mode_refinement": "true",
        "skip_detect_commands": "false",
        "skip_dev_story": "false",
        "skip_qa_automation": "false",
        "skip_code_review": "false",
        "skip_e2e_automation": "true",
        "skip_commit_and_push": "false",
        "skip_create_pull_request": "false",
        "skip_epic_architect": "true",
        "slack_verbose": "false",
        "slack_thread_ts": "",
        "branch": "",
        "extra_flags": "",
        "guidance": "",
        "execution_mode": "inline",
        "auto_execute_issue": "false",
        "code_agent": "",
    }
