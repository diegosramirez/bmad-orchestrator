"""Workflow dispatch inputs for Forge-initiated Discovery runs (epic-only, no dev/QA/PR)."""
from __future__ import annotations

DISCOVERY_SECRET_HEADER = "X-BMAD-Discovery-Secret"
# Preferred header for Forge apps (Discovery + Epic Architect); Discovery header remains supported.
FORGE_SECRET_HEADER = "X-BMAD-Forge-Secret"


def team_id_from_issue_key(issue_key: str, *, default_team_id: str) -> str:
    """Derive project prefix from Jira key (e.g. SAM1-275 -> SAM1)."""
    if "-" in issue_key:
        return issue_key.split("-", 1)[0]
    return default_team_id


def build_discovery_workflow_inputs(
    *,
    issue_key: str,
    target_repo: str,
    team_id: str,
) -> dict[str, str]:
    """Build GitHub Actions workflow_dispatch inputs for a Discovery-only run.

    Only ``check_epic_state`` and ``create_or_correct_epic`` run real work; every
    other skippable node is skipped. Uses ``execution_mode`` ``discovery`` so the
    graph ends without creating a GitHub Issue (no workflow checkbox required).
    """
    extra_flags = f"--epic-key {issue_key} --story-key {issue_key}"
    # workflow_dispatch inputs are string-valued; booleans as "true"/"false".
    return {
        "target_repo": target_repo,
        "base_branch": "main",
        "prompt": issue_key,
        "team_id": team_id,
        "run_id": "",
        "skip_check_epic_state": "false",
        "skip_create_or_correct_epic": "false",
        "skip_create_story_tasks": "true",
        "skip_party_mode_refinement": "true",
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
        "execution_mode": "discovery",
        "auto_execute_issue": "false",
        "code_agent": "",
    }
