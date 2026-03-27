"""Update Jira story customfield_10145 (BMAD Branch) with the current git branch name."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "update_jira_branch"


def make_update_jira_branch_node(
    jira: JiraServiceProtocol,
    settings: Settings,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Return a node that writes branch_name to the story's customfield_10145 (BMAD Branch)."""

    def update_jira_branch(state: OrchestratorState) -> dict[str, Any]:
        story_key = state.get("current_story_id")
        branch_name = state.get("branch_name")
        now = datetime.now(UTC).isoformat()
        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": "",
            "dry_run": settings.dry_run,
        }

        if not story_key or not branch_name:
            log_entry["message"] = (
                "Missing story_key or branch_name; skipping Jira branch field update."
            )
            return {"execution_log": [log_entry]}

        try:
            jira.set_story_branch_field(story_key, branch_name)
        except Exception:  # noqa: BLE001
            logger.warning(
                "jira_branch_field_update_failed",
                story_key=story_key,
            )
            log_entry["message"] = (
                "Failed to update Jira branch field "
                "(non-blocking)"
            )
            return {"execution_log": [log_entry]}

        log_entry["message"] = (
            f"Updated Jira field customfield_10145 "
            f"with branch {branch_name}"
        )
        return {"execution_log": [log_entry]}

    return update_jira_branch
