from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.git_service import GitService
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "commit_and_push"

_COMMIT_TEMPLATE = """\
feat({team_id}): implement story {story_id} [BMAD-ORCHESTRATED]

Summary:
{summary_lines}

Artifacts:
- epic updated: {epic_id}
- story updated: {story_id}
- qa automation added
"""


def make_commit_and_push_node(
    git: GitService,
    settings: Settings,
) -> Callable[[OrchestratorState], dict[str, Any]]:

    def commit_and_push(state: OrchestratorState) -> dict[str, Any]:
        team_id = state["team_id"]
        story_id = state["current_story_id"] or "UNKNOWN"
        epic_id = state["current_epic_id"] or "UNKNOWN"
        story_content = state["story_content"] or state["input_prompt"]
        existing_commit_sha = state["commit_sha"]

        now = datetime.now(UTC).isoformat()
        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": "",
            "dry_run": settings.dry_run,
        }

        # Idempotency: if already committed, skip
        if existing_commit_sha:
            log_entry["message"] = f"Already committed as {existing_commit_sha[:12]}, skipping"
            return {
                "commit_sha": existing_commit_sha,
                "execution_log": [log_entry],
            }

        # Capture current branch as the PR base before switching
        base_branch = git.get_current_branch()

        branch_name = git.make_branch_name(team_id, story_id, state["input_prompt"][:60])

        # Summarise the story content for the commit message
        summary_lines = "\n".join(
            f"- {line.strip()}"
            for line in story_content.splitlines()[:5]
            if line.strip()
        )

        commit_message = _COMMIT_TEMPLATE.format(
            team_id=team_id,
            story_id=story_id,
            summary_lines=summary_lines or f"- {state['input_prompt'][:100]}",
            epic_id=epic_id,
        )

        git.create_and_checkout_branch(branch_name)
        seen: set[str] = set()
        for path in (state.get("touched_files") or []):
            if path in seen:
                continue
            seen.add(path)
            if Path(path).exists():
                git.stage_path(path)
            else:
                logger.info("skip_stage_missing_path", path=path)
        if git.has_staged_changes():
            sha = git.commit(commit_message) or "dry-run-sha"
        else:
            # Check if HEAD differs from base — distinguishes a genuine resume
            # (commit succeeded but push failed) from "no files were changed".
            head_sha = git.get_head_sha()
            base_sha = git.rev_parse(base_branch)
            if head_sha == base_sha:
                logger.warning("no_changes_to_commit", branch=branch_name)
                log_entry["message"] = "No files changed — nothing to commit or push"
                return {
                    "base_branch": base_branch,
                    "branch_name": branch_name,
                    "commit_sha": None,
                    "execution_log": [log_entry],
                }
            # Retry scenario: commit succeeded in a previous run but push failed.
            # LangGraph didn't save the state update (nodes only update state on
            # return, never on exception). Re-use current HEAD sha and proceed to push.
            logger.info("skip_commit_already_done_resuming")
            sha = head_sha or "dry-run-sha"
        git.push(branch_name)

        log_entry["message"] = f"Committed {sha[:12]} to branch {branch_name}"
        return {
            "base_branch": base_branch,
            "branch_name": branch_name,
            "commit_sha": sha,
            "execution_log": [log_entry],
        }

    return commit_and_push
