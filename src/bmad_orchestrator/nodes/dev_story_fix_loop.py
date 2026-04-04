from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.code_review import _MEDIUM_OR_ABOVE
from bmad_orchestrator.nodes.dev_story import _resolve_cwd, _run_all_checks
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.cost_tracking import accumulate_cost
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "dev_story_fix_loop"


def make_fix_loop_node(
    agent: ClaudeAgentService,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("developer", settings.bmad_install_dir)

    def dev_story_fix_loop(state: OrchestratorState) -> dict[str, Any]:
        issues = state["code_review_issues"]
        loop_count = state["review_loop_count"]
        story_content = state["story_content"] or ""
        acceptance_criteria = state["acceptance_criteria"] or []
        guidance = state.get("retry_guidance") or ""
        dev_guidelines = state.get("dev_guidelines") or ""
        build_commands = state.get("build_commands") or []
        test_commands = state.get("test_commands") or []
        lint_commands = state.get("lint_commands") or []

        medium_plus = [i for i in issues if i["severity"] in _MEDIUM_OR_ABOVE]
        now = datetime.now(UTC).isoformat()
        cwd_path = str(_resolve_cwd(settings, state))

        _MAX_ISSUE_DESC = 200
        issues_text = "\n".join(
            f"- [{i['severity'].upper()}] {i['file']}: "
            f"{i['description'][:_MAX_ISSUE_DESC]}"
            for i in medium_plus
        )
        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)
        guidance_block = (
            f"Additional guidance from user:\n{guidance}\n\n" if guidance else ""
        )

        project_context = state.get("project_context") or ""
        ctx_block = (
            f"Target project context:\n{project_context}\n\n"
            if project_context else ""
        )

        guidelines_block = (
            f"## Project development guidelines\n{dev_guidelines}\n\n"
            if dev_guidelines else ""
        )
        obligations_lines = []
        if build_commands:
            obligations_lines.append(f"  Build: {' && '.join(build_commands)}")
        if test_commands:
            obligations_lines.append(f"  Test:  {' && '.join(test_commands)}")
        if lint_commands:
            obligations_lines.append(f"  Lint:  {' && '.join(lint_commands)}")
        obligations_block = (
            "## Verification commands — run these after fixing:\n"
            + "\n".join(obligations_lines)
            + "\n\nIf any command fails, fix the issues and re-run until all pass.\n\n"
        ) if obligations_lines else ""

        touched_files = state.get("touched_files") or []
        unique_files = list(dict.fromkeys(touched_files))

        # Pre-inject file contents so the agent doesn't burn turns reading
        cwd_for_read = _resolve_cwd(settings, state)
        _MAX_FILE_CHARS = 3000
        _MAX_TOTAL_CHARS = 30000
        file_contents_parts: list[str] = []
        total_chars = 0
        for fpath in unique_files:
            full = cwd_for_read / fpath if not Path(fpath).is_absolute() else Path(fpath)
            if not full.exists() or not full.is_file():
                continue
            try:
                content = full.read_text(encoding="utf-8")[:_MAX_FILE_CHARS]
                block = f"### {fpath}\n```\n{content}\n```"
                if total_chars + len(block) > _MAX_TOTAL_CHARS:
                    break
                file_contents_parts.append(block)
                total_chars += len(block)
            except Exception:
                continue

        if file_contents_parts:
            files_block = (
                "## Current file contents (pre-loaded — do NOT re-read these):\n\n"
                + "\n\n".join(file_contents_parts)
            )
        else:
            files_list = "\n".join(f"- {f}" for f in unique_files)
            files_block = f"## Files to read and fix:\n{files_list}"

        prompt = (
            f"{ctx_block}"
            f"{guidance_block}"
            f"{guidelines_block}"
            f"{obligations_block}"
            f"Fix code review issues (loop {loop_count + 1}).\n\n"
            f"IMPORTANT — Working directory and project context:\n"
            f"- Your CWD is: {cwd_path}\n"
            f"- Use RELATIVE paths (e.g. src/app/foo.ts) for all file operations.\n"
            f"- Do NOT re-read files already shown below.\n\n"
            f"Story context:\n{story_content}\n\n"
            f"Acceptance Criteria:\n{ac_text}\n\n"
            f"Issues to fix:\n{issues_text}\n\n"
            f"{files_block}\n\n"
            f"Instructions:\n"
            f"1. Fix ONLY the listed issues — do NOT rewrite unrelated files.\n"
            f"2. If build/tests pass now, your fixes must NOT break them.\n"
            f"3. Preserve all working logic — only change what is needed.\n"
            f"4. Cross-check class names, imports, and identifiers across files.\n"
            f"5. After fixing, run the verification commands above.\n"
            f"6. If any command fails, fix the issues and re-run until all pass.\n"
            f"7. Keep your final summary brief (under 500 words)."
        )

        test_failure = state.get("test_failure_output") or ""
        if test_failure:
            _MAX_FAILURE = 4000
            _ENV_PATTERNS = (
                "Cannot find name",
                "Cannot find namespace",
                "Cannot find type definition",
                "Cannot find module",
                "Module not found",
                "command not found",
                "not found",
                "ENOENT",
            )
            is_env_issue = any(p in test_failure for p in _ENV_PATTERNS)
            if is_env_issue:
                header = (
                    "## ENVIRONMENT/DEPENDENCY ISSUE — fix config before code:\n"
                    "The errors below suggest missing dependencies or type "
                    "definitions. Check package.json dependencies, "
                    "tsconfig.json type roots, and run `npm install` before "
                    "attempting code-level fixes.\n"
                )
            else:
                header = "## TEST FAILURES — MUST FIX BEFORE ANYTHING ELSE:\n"
            prompt += f"\n\n{header}{test_failure[:_MAX_FAILURE]}\n"

        result = agent.run_agent(
            prompt,
            system_prompt=system_prompt,
            agent_id="developer",
            cwd=_resolve_cwd(settings, state),
            max_turns=20,
            on_event=on_event,
        )

        current_cost = state.get("total_cost_usd") or 0.0
        new_cost, budget_msg = accumulate_cost(current_cost, result, settings)

        touched = result.touched_files
        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"Fix loop {loop_count + 1}: agent fixed "
                f"{len(medium_plus)} medium+ issue(s), "
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
                "failure_state": result.result_text,
                "review_loop_count": loop_count + 1,
                "code_review_issues": [],
                "touched_files": touched,
                "total_cost_usd": new_cost,
                "execution_log": [log_entry, fail_log],
            }

        # ── Independent test validation ─────────────────────────────────────
        cwd = _resolve_cwd(settings, state)
        check_error: str | None = None
        if not settings.dry_run:
            check_error = _run_all_checks(
                build_commands=state.get("build_commands") or [],
                test_commands=state.get("test_commands") or [],
                lint_commands=state.get("lint_commands") or [],
                cwd=cwd,
                setup_commands=state.get("setup_commands") or [],
            )
            if check_error:
                logger.warning("fix_loop_tests_failed", error=check_error[:300])
            else:
                logger.info("fix_loop_tests_passed")

        # If agent touched nothing and checks still fail, this is likely an
        # infrastructure issue the agent cannot fix.  Set failure_state so
        # the router short-circuits to fail_with_state.
        if check_error and not touched:
            logger.error(
                "fix_loop_env_failure",
                error=check_error[:300],
                msg="Agent made no changes and checks still fail",
            )
            return {
                "review_loop_count": loop_count + 1,
                "code_review_issues": [],
                "tests_passing": False,
                "test_failure_output": check_error,
                "failure_state": (
                    "Build/test checks failed but the agent made no code "
                    "changes — likely an infrastructure issue (not a code "
                    f"problem).\nError: {check_error[:500]}"
                ),
                "touched_files": [],
                "total_cost_usd": new_cost,
                "execution_log": [log_entry],
            }

        if budget_msg:
            return {
                "review_loop_count": loop_count + 1,
                "code_review_issues": [],
                "tests_passing": check_error is None,
                "test_failure_output": check_error,
                "failure_state": budget_msg,
                "touched_files": touched,
                "total_cost_usd": new_cost,
                "execution_log": [log_entry],
            }

        return {
            "review_loop_count": loop_count + 1,
            "code_review_issues": [],
            "tests_passing": check_error is None,
            "test_failure_output": check_error,
            "touched_files": touched,
            "total_cost_usd": new_cost,
            "execution_log": [log_entry],
        }

    return dev_story_fix_loop
