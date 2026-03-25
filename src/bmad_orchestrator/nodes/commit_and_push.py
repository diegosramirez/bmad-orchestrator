from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.git_service import GitService, classify_push_error
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.retry import retry_on_subprocess_error

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
            log_entry["message"] = (
                f"Already committed as {existing_commit_sha[:12]}, "
                f"skipping"
            )
            return {
                "commit_sha": existing_commit_sha,
                "execution_log": [log_entry],
            }

        # ── Pre-flight checks ──────────────────────────────────────
        if git.is_detached_head():
            msg = (
                "Git is in detached HEAD state. Cannot create a "
                "branch. Check out a branch (e.g. `git checkout "
                "main`) and retry."
            )
            log_entry["message"] = msg
            return {
                "failure_state": msg,
                "execution_log": [log_entry],
            }

        if git.has_uncommitted_changes():
            logger.warning(
                "dirty_working_tree",
                hint="Only touched_files will be staged; "
                "other changes ignored.",
            )

        # ── Branch setup ───────────────────────────────────────────
        current_branch = git.get_current_branch()
        on_existing_bmad_branch = current_branch.startswith("bmad/")

        if on_existing_bmad_branch:
            branch_name = current_branch
            base_branch = settings.github_base_branch or "main"
        else:
            base_branch = current_branch
            branch_name = git.make_branch_name(
                team_id, story_id, state["input_prompt"][:60],
            )

        # ── Commit message ─────────────────────────────────────────
        summary_lines = "\n".join(
            f"- {line.strip()}"
            for line in story_content.splitlines()[:5]
            if line.strip()
        )
        commit_message = _COMMIT_TEMPLATE.format(
            team_id=team_id,
            story_id=story_id,
            summary_lines=(
                summary_lines or f"- {state['input_prompt'][:100]}"
            ),
            epic_id=epic_id,
        )

        # ── Stage & commit ─────────────────────────────────────────
        if not on_existing_bmad_branch:
            git.create_and_checkout_branch(branch_name)

        seen: set[str] = set()
        for path in state.get("touched_files") or []:
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
            head_sha = git.get_head_sha()
            base_sha = git.rev_parse(base_branch)
            if head_sha == base_sha:
                if state.get("failure_state"):
                    logger.info(
                        "empty_commit_for_failure_pr",
                        branch=branch_name,
                    )
                    sha = git.commit(
                        commit_message, allow_empty=True,
                    ) or "dry-run-sha"
                else:
                    logger.warning(
                        "no_changes_to_commit", branch=branch_name,
                    )
                    log_entry["message"] = (
                        "No files changed — nothing to commit or push"
                    )
                    return {
                        "base_branch": base_branch,
                        "branch_name": branch_name,
                        "commit_sha": None,
                        "execution_log": [log_entry],
                    }
            else:
                logger.info("skip_commit_already_done_resuming")
                sha = head_sha or "dry-run-sha"

        # ── Push with retry ────────────────────────────────────────
        try:
            retry_on_subprocess_error(
                lambda: git.push(branch_name),
                label="git_push",
            )
        except subprocess.CalledProcessError as exc:
            category = classify_push_error(exc)
            stderr_snippet = (exc.stderr or "")[:300]
            error_msgs = {
                "auth": (
                    f"Push failed: authentication error. "
                    f"Check BMAD_GITHUB_TOKEN. "
                    f"stderr: {stderr_snippet}"
                ),
                "rejected": (
                    f"Push rejected (likely force-push protection "
                    f"or diverged history). "
                    f"stderr: {stderr_snippet}"
                ),
                "network": (
                    f"Push failed after retry: network error. "
                    f"stderr: {stderr_snippet}"
                ),
            }
            msg = error_msgs.get(
                category,
                f"Push failed ({category}). "
                f"stderr: {stderr_snippet}",
            )
            log_entry["message"] = msg
            return {
                "failure_state": msg,
                "base_branch": base_branch,
                "branch_name": branch_name,
                "commit_sha": sha,
                "execution_log": [log_entry],
            }

        # ── Merge conflict detection (best-effort) ────────────────
        merge_warning = ""
        try:
            if not git.can_merge_cleanly(branch_name, base_branch):
                merge_warning = (
                    " (merge conflicts detected with "
                    f"{base_branch} — manual resolution needed)"
                )
                logger.warning(
                    "merge_conflicts_detected",
                    head=branch_name,
                    base=base_branch,
                )
        except Exception:  # noqa: BLE001
            pass

        log_entry["message"] = (
            f"Committed {sha[:12]} to branch "
            f"{branch_name}{merge_warning}"
        )
        return {
            "base_branch": base_branch,
            "branch_name": branch_name,
            "commit_sha": sha,
            "execution_log": [log_entry],
        }

    return commit_and_push
