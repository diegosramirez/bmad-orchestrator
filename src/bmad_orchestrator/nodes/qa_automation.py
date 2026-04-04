from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.dev_story import _resolve_cwd, _run_all_checks
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState, QAResult
from bmad_orchestrator.utils.cost_tracking import accumulate_cost
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.project_context import find_example_test_file

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

        # Find an existing test file as a reference for the correct patterns
        cwd = _resolve_cwd(settings, state)
        example_test = find_example_test_file(cwd) if not settings.dry_run else ""
        example_block = (
            f"## Reference — existing test file from this project:\n"
            f"Follow the EXACT same test framework, imports, and patterns "
            f"shown in this file. Do NOT use a different test library.\n\n"
            f"{example_test}\n\n"
        ) if example_test else ""

        prompt = (
            f"{ctx_block}"
            f"{guidance_block}"
            f"{example_block}"
            f"Write automated tests for the following story.\n\n"
            f"IMPORTANT — Working directory and project context:\n"
            f"- Your CWD is: {cwd_path}\n"
            f"- Use RELATIVE paths (e.g. src/app/foo.spec.ts) for all file operations.\n"
            f"- Project context is provided above — do NOT re-read package.json, "
            f"angular.json, tsconfig.json, or other config files unless you need "
            f"specific details not in the context.\n"
            f"- Use the EXACT test framework and patterns shown in the reference "
            f"test file above. Do NOT use a different test library or syntax.\n"
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
            cwd=cwd,
            max_turns=15,
            on_event=on_event,
        )

        touched = result.touched_files
        current_cost = state.get("total_cost_usd") or 0.0
        new_cost, budget_msg = accumulate_cost(current_cost, result, settings)

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
                setup_commands=state.get("setup_commands") or [],
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

        base = {
            "qa_results": qa_results,
            "tests_passing": tests_passing,
            "test_failure_output": check_error,
            "execution_log": [log_entry],
            "touched_files": touched,
            "total_cost_usd": new_cost,
        }
        if budget_msg:
            base["failure_state"] = budget_msg
        return base

    return qa_automation
