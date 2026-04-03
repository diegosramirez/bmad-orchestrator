from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.project_context import read_manifest_scripts

logger = get_logger(__name__)

NODE_NAME = "detect_commands"


class ProjectCommands(BaseModel):
    """AI-detected build/test/lint commands for the target project."""

    setup: list[str] = Field(
        default_factory=list,
        description=(
            "Shell commands to install dependencies / bootstrap the project "
            "(e.g. 'npm install', 'dotnet restore', 'pip install -e .', "
            "'go mod download', 'cargo fetch'). Run BEFORE build/test/lint."
        ),
    )
    build: list[str] = Field(
        default_factory=list,
        description="Shell commands to compile/build the project (e.g. 'npm run build')",
    )
    test: list[str] = Field(
        default_factory=list,
        description="Shell commands to run the test suite in non-interactive/CI mode",
    )
    lint: list[str] = Field(
        default_factory=list,
        description="Shell commands to lint or check code style",
    )
    e2e: list[str] = Field(
        default_factory=list,
        description=(
            "Shell commands to run E2E/browser tests (e.g. 'npx playwright test'). "
            "Separate from unit test commands."
        ),
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of why these commands were chosen",
    )


def make_detect_commands_node(
    claude: ClaudeService,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Factory for the detect_commands node.

    Uses Claude to determine the correct build, test, and lint commands
    from the project context, dev guidelines, and manifest scripts.
    """

    def detect_commands(state: OrchestratorState) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()

        project_context = state.get("project_context") or ""
        dev_guidelines = state.get("dev_guidelines") or ""
        cwd = Path.cwd()
        manifest_scripts = read_manifest_scripts(cwd)

        if settings.dry_run:
            log_entry: ExecutionLogEntry = {
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Skipped command detection (dry run)",
                "dry_run": True,
            }
            return {"execution_log": [log_entry]}

        scripts_block = ""
        if manifest_scripts:
            scripts_block = (
                "\n\n## Project manifest scripts\n"
                f"```json\n{json.dumps(manifest_scripts, indent=2)}\n```"
            )

        result = claude.complete_structured(
            system_prompt=(
                "You are a build systems expert. Analyse the project context and "
                "determine the exact shell commands needed to build, test, and lint "
                "this project."
            ),
            user_message=(
                f"## Project context\n{project_context}\n\n"
                f"## Development guidelines\n{dev_guidelines}"
                f"{scripts_block}\n\n"
                "Based on the above, determine the correct shell commands for:\n"
                "0. **setup** — install dependencies / restore packages. Examples: "
                "`npm install`, `yarn install`, `pnpm install`, `dotnet restore`, "
                "`pip install -e .`, `uv sync`, `go mod download`, `cargo fetch`, "
                "`./gradlew dependencies`, `composer install`, `bundle install`. "
                "Return the single command appropriate for this project's package "
                "manager. If unsure, return an empty list.\n"
                "1. **build** — compile or bundle the project\n"
                "2. **test** — run the unit/integration test suite in non-interactive/CI "
                "mode (no --watch, no interactive prompts)\n"
                "3. **lint** — lint or check code style\n"
                "4. **e2e** — run end-to-end / browser tests (Playwright, Cypress). "
                "If the project has explicit E2E scripts or Playwright/Cypress config, "
                "return the project-specific command. Otherwise, return "
                "`['npx playwright test']` as the default.\n\n"
                "Rules:\n"
                "- Only return commands the project actually supports based on the "
                "manifest scripts and config files shown above.\n"
                "- Return setup commands SEPARATELY from build commands. Setup = "
                "installing dependencies. Build = compiling / verifying code "
                "correctness.\n"
                "- ALWAYS use `npm run <script>` (or `yarn <script>`, `pnpm <script>`) "
                "to invoke manifest scripts — NEVER use bare binary names like `ng`, "
                "`tsc`, `jest`, `vitest` etc. directly. For example, if the manifest "
                "has `\"build\": \"ng build\"`, return `npm run build`, NOT `ng build`. "
                "If you need to add flags not in the manifest script, use "
                "`npx <binary> <flags>` (e.g. `npx ng test --watch=false`).\n"
                "- Build commands should only verify code correctness AFTER the "
                "environment is already set up (e.g. `npm run build`, "
                "`tsc --noEmit`).\n"
                "- For tests, ensure they run to completion (no watch mode). "
                "Use flags appropriate for the detected test runner.\n"
                "- If unsure about a category, return an empty list.\n"
                "- Do NOT invent scripts that aren't in the manifest."
            ),
            schema=ProjectCommands,
            max_tokens=1024,
            agent_id="build-expert",
            on_event=on_event,
        )

        logger.info(
            "commands_detected",
            setup=result.setup,
            build=result.build,
            test=result.test,
            lint=result.lint,
            e2e=result.e2e,
            reasoning=result.reasoning[:200],
        )

        log_entry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"Detected commands — setup: {result.setup}, "
                f"build: {result.build}, "
                f"test: {result.test}, lint: {result.lint}, e2e: {result.e2e}"
            ),
            "dry_run": False,
        }

        return {
            "setup_commands": result.setup,
            "build_commands": result.build,
            "test_commands": result.test,
            "lint_commands": result.lint,
            "e2e_commands": result.e2e,
            "execution_log": [log_entry],
        }

    return detect_commands
