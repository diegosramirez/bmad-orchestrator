from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.dev_story import _resolve_cwd
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.state import E2EResult, ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.project_context import run_project_command

logger = get_logger(__name__)

NODE_NAME = "e2e_automation"


def _run_e2e_checks(e2e_commands: list[str], cwd: Path) -> str | None:
    """Run E2E commands. Returns None if all pass, error string on failure."""
    for cmd in e2e_commands:
        success, output = run_project_command(cmd, cwd)
        if not success:
            return f"E2E failed (`{cmd}`):\n{output}"
    return None


def make_e2e_automation_node(
    agent: ClaudeAgentService,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("e2e_tester", settings.bmad_install_dir)

    def e2e_automation(state: OrchestratorState) -> dict[str, Any]:
        e2e_commands = state.get("e2e_commands") or []
        now = datetime.now(UTC).isoformat()

        # Skip if no E2E commands configured (opt-in)
        if not e2e_commands:
            log_entry: ExecutionLogEntry = {
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Skipped — no E2E commands configured",
                "dry_run": settings.dry_run,
            }
            return {
                "e2e_tests_passing": True,
                "execution_log": [log_entry],
            }

        story_content = state["story_content"] or ""
        acceptance_criteria = state["acceptance_criteria"] or []
        project_context = state.get("project_context") or ""
        touched_files = state.get("touched_files") or []
        cwd_path = str(_resolve_cwd(settings, state))

        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)
        ctx_block = (
            f"Target project context:\n{project_context}\n\n" if project_context else ""
        )
        impl_files_list = "\n".join(f"- {f}" for f in dict.fromkeys(touched_files))
        e2e_cmds_text = "\n".join(f"  {cmd}" for cmd in e2e_commands)

        prompt = (
            f"{ctx_block}"
            f"Write end-to-end Playwright tests for the following story.\n\n"
            f"IMPORTANT — Working directory and project context:\n"
            f"- Your CWD is: {cwd_path}\n"
            f"- Use RELATIVE paths (e.g. e2e/foo.spec.ts) for all file operations.\n"
            f"- Use the project context above to understand the existing test setup.\n\n"
            f"Story:\n{story_content}\n\n"
            f"Acceptance Criteria:\n{ac_text}\n\n"
            f"## Implementation files (read these first):\n{impl_files_list}\n\n"
            f"Instructions:\n"
            f"1. Read the implementation files above to understand the actual code.\n"
            f"2. Write Playwright E2E tests that validate each acceptance criterion "
            f"from the user's perspective.\n"
            f"3. Use semantic locators: getByRole, getByLabel, getByText — avoid "
            f"CSS selectors.\n"
            f"4. Write ONE test file per tool call to avoid output token limits.\n"
            f"5. If playwright.config.ts doesn't exist, create it with a webServer "
            f"option to auto-start the dev server.\n"
            f"6. If Playwright is not installed, run `npx playwright install chromium` "
            f"before running tests.\n"
            f"7. Keep tests linear, deterministic, and independent.\n"
            f"8. Keep your final summary brief (under 500 words).\n"
        )
        if e2e_commands:
            prompt += (
                f"\n## Verification — run E2E tests after writing:\n{e2e_cmds_text}\n\n"
                f"If tests fail, fix the test files and re-run until they pass."
            )

        result = agent.run_agent(
            prompt,
            system_prompt=system_prompt,
            agent_id="e2e_tester",
            cwd=_resolve_cwd(settings, state),
            max_turns=15,
            max_budget_usd=3.0,
            on_event=on_event,
        )

        touched = result.touched_files

        e2e_results: list[E2EResult] = [
            {
                "test_file": "agent_self_verified",
                "passed": not result.is_error,
                "output": result.result_text or "(no output)",
            }
        ]

        # ── Independent E2E validation ───────────────────────────────────────
        cwd = _resolve_cwd(settings, state)
        check_error: str | None = None
        if not settings.dry_run:
            check_error = _run_e2e_checks(e2e_commands, cwd)
            if check_error:
                logger.warning("e2e_tests_failed", error=check_error[:300])
            else:
                logger.info("e2e_tests_passed")

        tests_passing = check_error is None

        log_entry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"Agent wrote {len(touched)} E2E test file(s); "
                f"independent validation: "
                f"{'PASS' if tests_passing else 'FAIL'}"
            ),
            "dry_run": settings.dry_run,
        }

        return {
            "e2e_results": e2e_results,
            "e2e_tests_passing": tests_passing,
            "e2e_failure_output": check_error,
            "execution_log": [log_entry],
            "touched_files": touched,
        }

    return e2e_automation


def make_e2e_router(
    settings: Settings,
) -> Callable[[OrchestratorState], str]:
    """Conditional edge after e2e_automation.

    Routes to commit_and_push on success or exhausted loops,
    e2e_fix_loop when failures are fixable.
    E2E failures are non-blocking in v1 — exhausted loops still commit.
    """

    def route(state: OrchestratorState) -> str:
        if not state.get("e2e_commands"):
            return "commit_and_push"
        if state.get("e2e_tests_passing") is True:
            return "commit_and_push"
        if state["e2e_loop_count"] < settings.max_e2e_loops:
            return "e2e_fix_loop"
        return "commit_and_push"

    return route
