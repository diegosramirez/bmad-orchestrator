from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.dev_story import _resolve_cwd, _run_all_checks
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState, QAResult
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "qa_automation"


def make_qa_automation_node(
    agent: ClaudeAgentService,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("qa", settings.bmad_install_dir)

    def qa_automation(state: OrchestratorState) -> dict[str, Any]:
        story_content = state["story_content"] or ""
        acceptance_criteria = state["acceptance_criteria"] or []
        guidance = state.get("retry_guidance") or ""
        project_context = state.get("project_context") or ""
        test_commands = state.get("test_commands") or []
        touched_files = state.get("touched_files") or []
        now = datetime.now(UTC).isoformat()
        cwd_path = str(_resolve_cwd(settings, state))

        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)
        guidance_block = (
            f"Additional guidance from user:\n{guidance}\n\n" if guidance else ""
        )
        ctx_block = (
            f"Target project context:\n{project_context}\n\n" if project_context else ""
        )

        impl_files_list = "\n".join(f"- {f}" for f in dict.fromkeys(touched_files))
        test_cmds_text = "\n".join(f"  {cmd}" for cmd in test_commands)

        prompt = (
            f"{ctx_block}"
            f"{guidance_block}"
            f"Write automated tests for the following story.\n\n"
            f"IMPORTANT — Working directory and project context:\n"
            f"- Your CWD is: {cwd_path}\n"
            f"- Use RELATIVE paths (e.g. src/app/foo.spec.ts) for all file operations.\n"
            f"- Project context is provided above — do NOT re-read package.json, "
            f"angular.json, tsconfig.json, or other config files unless you need "
            f"specific details not in the context.\n"
            f"- Use the test framework identified in the project context above.\n"
            f"- Do NOT explore the project to discover the test framework.\n\n"
            f"Story:\n{story_content}\n\n"
            f"Acceptance Criteria:\n{ac_text}\n\n"
            f"## Implementation files to test (read these first):\n{impl_files_list}\n\n"
            f"Instructions:\n"
            f"1. Read the implementation files above to understand the actual code.\n"
            f"2. Write ONE test file per tool call — never combine multiple files "
            f"in a single response. This avoids output token limits.\n"
            f"3. Write test files that cover every acceptance criterion.\n"
            f"4. Include edge cases and failure modes.\n"
            f"5. Import from the ACTUAL implementation files — use exact class names, "
            f"function names, and file paths.\n"
            f"6. Only create test files — do NOT modify implementation code.\n"
            f"7. Keep your final summary brief (under 500 words).\n"
        )
        if test_commands:
            prompt += (
                f"\n## Verification — run tests after writing:\n{test_cmds_text}\n\n"
                f"If tests fail, fix the test files and re-run until they pass."
            )

        result = agent.run_agent(
            prompt,
            system_prompt=system_prompt,
            agent_id="qa",
            cwd=_resolve_cwd(settings, state),
            max_turns=10,
            on_event=on_event,
        )

        touched = result.touched_files

        # The agent already runs test commands as part of its self-verification
        # loop (see prompt instructions above).  We record a summary result
        # rather than re-running the same commands a second time.
        qa_results: list[QAResult] = [
            {
                "test_file": "agent_self_verified",
                "passed": not result.is_error,
                "output": result.result_text or "(no output)",
            }
        ]

        # ── Independent test validation ─────────────────────────────────────
        cwd = _resolve_cwd(settings, state)
        check_error: str | None = None
        if not settings.dry_run:
            check_error = _run_all_checks(
                build_commands=state.get("build_commands") or [],
                test_commands=state.get("test_commands") or [],
                lint_commands=[],
                cwd=cwd,
            )
            if check_error:
                logger.warning("qa_tests_failed", error=check_error[:300])
            else:
                logger.info("qa_tests_passed")

        tests_passing = check_error is None

        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"Agent wrote {len(touched)} test file(s); "
                f"independent validation: "
                f"{'PASS' if tests_passing else 'FAIL'}"
            ),
            "dry_run": settings.dry_run,
        }

        return {
            "qa_results": qa_results,
            "tests_passing": tests_passing,
            "test_failure_output": check_error,
            "execution_log": [log_entry],
            "touched_files": touched,
        }

    return qa_automation
