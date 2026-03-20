from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.dev_story import _resolve_cwd
from bmad_orchestrator.nodes.e2e_automation import _DEFAULT_E2E_COMMANDS, _run_e2e_checks
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "e2e_fix_loop"


def make_e2e_fix_loop_node(
    agent: ClaudeAgentService,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("developer", settings.bmad_install_dir)

    def e2e_fix_loop(state: OrchestratorState) -> dict[str, Any]:
        loop_count = state["e2e_loop_count"]
        story_content = state["story_content"] or ""
        acceptance_criteria = state["acceptance_criteria"] or []
        e2e_commands = state.get("e2e_commands") or _DEFAULT_E2E_COMMANDS
        e2e_failure = state.get("e2e_failure_output") or ""
        now = datetime.now(UTC).isoformat()
        cwd_path = str(_resolve_cwd(settings, state))

        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)

        project_context = state.get("project_context") or ""
        ctx_block = (
            f"Target project context:\n{project_context}\n\n"
            if project_context else ""
        )

        touched_files = state.get("touched_files") or []
        files_list = "\n".join(f"- {f}" for f in dict.fromkeys(touched_files))

        e2e_cmds_text = "\n".join(f"  {cmd}" for cmd in e2e_commands)

        prompt = (
            f"{ctx_block}"
            f"Fix E2E test failures (loop {loop_count + 1}).\n\n"
            f"IMPORTANT — Working directory and project context:\n"
            f"- Your CWD is: {cwd_path}\n"
            f"- Use RELATIVE paths (e.g. src/app/foo.ts) for all file operations.\n"
            f"- Do NOT re-read config files. Go straight to the listed files.\n\n"
            f"Story context:\n{story_content}\n\n"
            f"Acceptance Criteria:\n{ac_text}\n\n"
            f"## Files to read and fix:\n{files_list}\n\n"
            f"## E2E Verification commands — run after fixing:\n{e2e_cmds_text}\n\n"
            f"Instructions:\n"
            f"1. Read the E2E test files and implementation files listed above.\n"
            f"2. Determine whether the failure is in the implementation or the "
            f"test code.\n"
            f"3. Fix the root cause — prefer fixing implementation bugs over "
            f"weakening tests.\n"
            f"4. After fixing, run the E2E verification commands above.\n"
            f"5. If tests still fail, fix and re-run until they pass.\n"
            f"6. Keep your final summary brief (under 500 words).\n"
        )

        if e2e_failure:
            _MAX_FAILURE = 2000
            prompt += (
                f"\n## E2E FAILURES — MUST FIX:\n"
                f"{e2e_failure[:_MAX_FAILURE]}\n"
            )

        result = agent.run_agent(
            prompt,
            system_prompt=system_prompt,
            agent_id="developer",
            cwd=_resolve_cwd(settings, state),
            max_turns=10,
            on_event=on_event,
        )

        touched = result.touched_files
        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"E2E fix loop {loop_count + 1}: "
                f"touched {len(touched)} file(s)"
            ),
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
                "e2e_loop_count": loop_count + 1,
                "e2e_tests_passing": False,
                "e2e_failure_output": result.result_text,
                "touched_files": touched,
                "execution_log": [log_entry, fail_log],
            }

        # ── Independent E2E validation ───────────────────────────────────────
        cwd = _resolve_cwd(settings, state)
        check_error: str | None = None
        if not settings.dry_run:
            check_error = _run_e2e_checks(e2e_commands, cwd)
            if check_error:
                logger.warning("e2e_fix_loop_failed", error=check_error[:300])
            else:
                logger.info("e2e_fix_loop_passed")

        return {
            "e2e_loop_count": loop_count + 1,
            "e2e_tests_passing": check_error is None,
            "e2e_failure_output": check_error,
            "touched_files": touched,
            "execution_log": [log_entry],
        }

    return e2e_fix_loop
