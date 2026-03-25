"""Workflow dispatch inputs for Forge-initiated Epic Architect runs (epic_architect mode)."""
from __future__ import annotations

from bmad_orchestrator.webhook.discovery import team_id_from_issue_key

__all__ = ["build_epic_architect_workflow_inputs", "team_id_from_issue_key"]


def build_epic_architect_workflow_inputs(
    *,
    issue_key: str,
    target_repo: str,
    team_id: str,
) -> dict[str, str]:
    """Build GitHub Actions workflow_dispatch inputs for Epic Architect (Design Architect) only.

    Skips every skippable node except ``epic_architect`` (``skip_epic_architect`` false).
    Uses ``execution_mode`` ``epic_architect`` so the graph routes to ``epic_architect`` -> END.
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
        "skip_create_story_tasks": "true",
        "skip_party_mode_refinement": "true",
        "skip_detect_commands": "true",
        "skip_dev_story": "true",
        "skip_qa_automation": "true",
        "skip_code_review": "true",
        "skip_e2e_automation": "true",
        "skip_commit_and_push": "true",
        "skip_create_pull_request": "true",
        "skip_epic_architect": "false",
        "slack_verbose": "false",
        "slack_thread_ts": "",
        "branch": "",
        "extra_flags": extra_flags,
        "guidance": "",
        "execution_mode": "epic_architect",
        "auto_execute_issue": "false",
        "code_agent": "",
    }
