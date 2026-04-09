from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.cost_tracking import accumulate_cost
from bmad_orchestrator.utils.jira_checklist_text import mark_checklist_items_done
from bmad_orchestrator.utils.json_repair import parse_stringified_list
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.project_context import run_compile_check, run_project_command

logger = get_logger(__name__)

NODE_NAME = "dev_story"


class FileOperationModel(BaseModel):
    action: Literal["create", "modify", "delete"]
    path: str = Field(description="Relative path from the repository root")
    content: str = Field(default="", description="Full file content for create/modify")


class FileOperationList(BaseModel):
    """Kept for tests and dry-run construction."""

    operations: list[FileOperationModel]

    @field_validator("operations", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        """Handle Claude returning operations as a JSON string."""
        return parse_stringified_list(v)


class FilePlanItem(BaseModel):
    action: Literal["create", "modify", "delete"]
    path: str = Field(description="Relative path from the repository root")
    description: str = Field(description="Brief purpose of this file / what changes")


class FilePlan(BaseModel):
    """Phase-1 output: list of files to touch, no content yet."""

    files: list[FilePlanItem]

    @field_validator("files", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


class FileContent(BaseModel):
    """Phase-2 output: complete content for a single file."""

    content: str = Field(description="Complete, production-ready file content")


class ChecklistCompletionAssessment(BaseModel):
    """Which checklist item summaries were fully completed in a dev session."""

    completed_task_summaries: list[str] = Field(default_factory=list)

    @field_validator("completed_task_summaries", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


def _truncate_session_text(text: str | None, max_len: int = 8000) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def maybe_update_jira_checklist_after_dev_session(
    jira: JiraServiceProtocol,
    claude: ClaudeService,
    settings: Settings,
    story_key: str | None,
    checklist_markdown: str,
    session_summary: str | None,
    acceptance_criteria: list[str],
    *,
    on_event: Callable[[str], None] | None,
) -> None:
    """Mark completed checklist items in Jira Checklist Text only (not comments)."""
    if not story_key or story_key == "UNKNOWN":
        return
    if not (checklist_markdown or "").strip():
        return

    sm_prompt = build_system_prompt("scrum_master", settings.bmad_install_dir)
    ac_lines = "\n".join(f"- {ac}" for ac in acceptance_criteria)
    user_msg = (
        "From the Jira implementation checklist and the development session output below, "
        "list which checklist items are FULLY completed in this session.\n\n"
        "Each checklist line has a bold **summary** — return those summary strings exactly "
        "as they appear in the checklist (or close enough to match the same line).\n"
        "Do not include items that are only partially done or not addressed.\n\n"
        f"## Checklist (from Jira)\n{checklist_markdown}\n\n"
        f"## Acceptance criteria\n{ac_lines or '(none)'}\n\n"
        "## Session output\n"
        f"{_truncate_session_text(session_summary)}\n\n"
        "Return JSON with field completed_task_summaries: array of strings."
    )
    try:
        assessment = claude.complete_structured(
            system_prompt=sm_prompt,
            user_message=user_msg,
            schema=ChecklistCompletionAssessment,
            agent_id="scrum_master",
            max_tokens=4096,
            on_event=on_event,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("checklist_completion_assessment_failed", error=str(exc)[:200])
        return

    new_md = mark_checklist_items_done(
        checklist_markdown,
        assessment.completed_task_summaries,
    )
    if new_md == checklist_markdown:
        return
    try:
        jira.set_story_checklist_text(story_key, new_md)
    except Exception as exc:  # noqa: BLE001
        logger.warning("checklist_jira_update_failed", story_key=story_key, error=str(exc)[:200])


def _prefix_output_dir(
    operations: list[FileOperationModel],
    story_id: str | None,
    artifacts_dir: str,
) -> list[FileOperationModel]:
    """Prefix all operation paths with <artifacts_dir>/<story_id>/."""
    prefix = Path(artifacts_dir) / (story_id or "unknown")
    prefixed: list[FileOperationModel] = []
    for op in operations:
        prefixed.append(op.model_copy(update={"path": str(prefix / op.path)}))
    return prefixed


def _apply_operations(operations: list[FileOperationModel], dry_run: bool) -> list[str]:
    """Apply file operations to disk. Returns list of touched file paths."""
    touched: list[str] = []
    for op in operations:
        path = Path(op.path)
        action = op.action
        if dry_run:
            logger.info("dry_run_file_op", action=action, path=str(path))
            touched.append(str(path))
            continue

        if action in ("create", "modify"):
            path.parent.mkdir(parents=True, exist_ok=True)
            new_hash = hashlib.sha256(op.content.encode()).hexdigest()
            if path.exists():
                old = path.read_text(encoding="utf-8").encode()
                existing_hash = hashlib.sha256(old).hexdigest()
                if existing_hash == new_hash:
                    logger.info("file_unchanged_skip", path=str(path))
                    touched.append(str(path))
                    continue
            path.write_text(op.content, encoding="utf-8")
            logger.info("file_written", action=action, path=str(path))
        elif action == "delete":
            if path.exists():
                path.unlink()
                logger.info("file_deleted", path=str(path))
        touched.append(str(path))
    return touched


def _run_all_checks(
    build_commands: list[str],
    test_commands: list[str],
    lint_commands: list[str],
    cwd: Path,
    *,
    setup_commands: list[str] | None = None,
) -> str | None:
    """Run setup, TypeScript compile check, then build/test/lint commands.

    Returns None if everything passes, or a human-readable error string on first failure.
    The developer calls this after writing files to self-verify before handing off.
    """
    for cmd in setup_commands or []:
        logger.info("setup_preflight", cmd=cmd, cwd=str(cwd))
        success, output = run_project_command(cmd, cwd)
        if not success:
            return f"Setup failed (`{cmd}`):\n{output}"

    compile_errors = run_compile_check(cwd)
    if compile_errors:
        return "TypeScript compile errors:\n" + "\n".join(compile_errors[:5])

    categories: list[tuple[str, list[str]]] = [
        ("build", build_commands),
        ("test", test_commands),
        ("lint", lint_commands),
    ]
    for category, commands in categories:
        for cmd in commands:
            success, output = run_project_command(cmd, cwd)
            if not success:
                return f"{category.title()} failed (`{cmd}`):\n{output}"
    return None


def _resolve_cwd(settings: Settings, state: OrchestratorState) -> Path:
    """Determine the working directory for the agent session."""
    if settings.artifacts_dir:
        story_id = state.get("current_story_id") or "unknown"
        return Path(settings.artifacts_dir) / story_id
    return Path.cwd()


def make_dev_story_node(
    agent: ClaudeAgentService,
    claude: ClaudeService,
    jira: JiraServiceProtocol,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("developer", settings.bmad_install_dir)

    def dev_story(state: OrchestratorState) -> dict[str, Any]:
        story_key = state.get("current_story_id")
        checklist_md = ""
        if story_key and story_key != "UNKNOWN":
            try:
                checklist_md = jira.get_story_checklist_text(story_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("checklist_read_failed", story_key=story_key, error=str(exc)[:200])

        story_content = state["story_content"] or ""
        acceptance_criteria = state["acceptance_criteria"] or []
        architect_output = state["architect_output"] or ""
        developer_output = state["developer_output"] or ""
        guidance = state.get("retry_guidance") or ""
        dev_guidelines = state.get("dev_guidelines") or ""
        build_commands = state.get("build_commands") or []
        test_commands = state.get("test_commands") or []
        lint_commands = state.get("lint_commands") or []

        now = datetime.now(UTC).isoformat()
        cwd_path = str(_resolve_cwd(settings, state))

        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)
        guidance_block = f"Additional guidance from user:\n{guidance}\n\n" if guidance else ""
        project_context = state.get("project_context") or ""
        ctx_block = f"Target project context:\n{project_context}\n\n" if project_context else ""

        guidelines_block = (
            f"## Project development guidelines\n{dev_guidelines}\n\n" if dev_guidelines else ""
        )
        obligations_lines = []
        if build_commands:
            obligations_lines.append(f"  Build: {' && '.join(build_commands)}")
        if test_commands:
            obligations_lines.append(f"  Test:  {' && '.join(test_commands)}")
        if lint_commands:
            obligations_lines.append(f"  Lint:  {' && '.join(lint_commands)}")
        obligations_block = (
            "## Verification commands — run these after writing all files:\n"
            + "\n".join(obligations_lines)
            + "\n\nIf any command fails, read the error, fix the relevant files, "
            "and re-run until all pass.\n\n"
        ) if obligations_lines else ""

        checklist_block = ""
        if checklist_md.strip():
            checklist_block = (
                "## Implementation checklist (from Jira)\n"
                f"{checklist_md}\n\n"
                "Work through these items as you implement; completed items will be "
                "reflected in Jira after this session.\n\n"
            )

        prompt = (
            f"{ctx_block}"
            f"{guidance_block}"
            f"{guidelines_block}"
            f"{obligations_block}"
            f"{checklist_block}"
            f"Implement the following user story.\n\n"
            f"IMPORTANT — Working directory and project context:\n"
            f"- Your CWD is: {cwd_path}\n"
            f"- Use RELATIVE paths (e.g. src/app/foo.ts) for all file operations.\n"
            f"- Project context is provided above — do NOT re-read package.json, "
            f"angular.json, tsconfig.json, or other config files unless you need "
            f"specific details not in the context.\n"
            f"- Start implementing immediately — do not spend turns exploring.\n\n"
            f"IMPORTANT — Keep it simple:\n"
            f"- Implement ONLY what the acceptance criteria require — nothing more.\n"
            f"- Do NOT add extra configurability, optional parameters, or "
            f"advanced features beyond what is asked.\n"
            f"- Prefer simple, direct implementations over clever abstractions.\n"
            f"- Fewer files with straightforward logic beats many files with "
            f"over-engineered patterns.\n"
            f"- If writing test files, first read an existing test file in the "
            f"project to match its framework and patterns exactly.\n\n"
            f"IMPORTANT: Every acceptance criterion below MUST be fully "
            f"implemented. The code reviewer will verify each one.\n\n"
            f"Story:\n{story_content}\n\n"
            f"Acceptance Criteria:\n{ac_text}\n\n"
            f"Architecture notes:\n{architect_output}\n\n"
            f"Implementation plan:\n{developer_output}\n\n"
            f"Instructions:\n"
            f"1. Write ONE file per tool call — never combine multiple files "
            f"in a single response. This avoids output token limits.\n"
            f"2. Use production-ready code with identical class names, selectors, "
            f"and identifiers across files.\n"
            f"3. If you modify package.json (add/remove dependencies), run "
            f"`npm install` before running verification commands.\n"
            f"4. After writing all files, run the verification commands above.\n"
            f"5. If any command fails, fix the issues and re-run until all pass.\n"
            f"6. Keep your final summary brief (under 500 words)."
        )

        result = agent.run_agent(
            prompt,
            system_prompt=system_prompt,
            agent_id="developer",
            cwd=_resolve_cwd(settings, state),
            max_turns=20,
            on_event=on_event,
        )

        touched = result.touched_files
        current_cost = state.get("total_cost_usd") or 0.0
        new_cost, budget_msg = accumulate_cost(current_cost, result, settings)

        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": f"Agent wrote {len(touched)} file(s): {', '.join(touched[:5])}",
            "dry_run": settings.dry_run,
        }

        if result.is_error:
            fail_log: ExecutionLogEntry = {
                "timestamp": now,
                "node": NODE_NAME,
                "message": f"Agent session error: {result.result_text or 'unknown'}",
                "dry_run": settings.dry_run,
            }
            return {
                "failure_state": result.result_text,
                "touched_files": touched,
                "total_cost_usd": new_cost,
                "execution_log": [log_entry, fail_log],
            }

        if budget_msg:
            return {
                "failure_state": budget_msg,
                "touched_files": touched,
                "total_cost_usd": new_cost,
                "execution_log": [log_entry],
            }

        maybe_update_jira_checklist_after_dev_session(
            jira,
            claude,
            settings,
            story_key,
            checklist_md,
            result.result_text,
            acceptance_criteria,
            on_event=on_event,
        )

        return {"execution_log": [log_entry], "touched_files": touched, "total_cost_usd": new_cost}

    return dev_story
