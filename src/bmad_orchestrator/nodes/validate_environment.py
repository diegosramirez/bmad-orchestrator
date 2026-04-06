from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.dev_story import _resolve_cwd
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.project_context import run_project_command

# Fallback setup commands when detect_commands was skipped.
# Maps manifest file → install command (technology-agnostic).
_MANIFEST_SETUP: list[tuple[str, str]] = [
    ("package-lock.json", "npm install"),
    ("yarn.lock", "yarn install"),
    ("pnpm-lock.yaml", "pnpm install"),
    ("package.json", "npm install"),
    ("requirements.txt", "pip install -r requirements.txt"),
    ("pyproject.toml", "pip install -e ."),
    ("go.mod", "go mod download"),
    ("Cargo.toml", "cargo fetch"),
    ("Gemfile", "bundle install"),
    ("composer.json", "composer install"),
]

logger = get_logger(__name__)

NODE_NAME = "validate_environment"


def make_validate_environment_node(
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Factory for the validate_environment node.

    Runs setup commands, then build and test commands to verify the
    environment is healthy before burning agent time on code generation.
    """

    def validate_environment(state: OrchestratorState) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        _emit = on_event or (lambda _: None)

        if settings.dry_run:
            log_entry: ExecutionLogEntry = {
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Skipped environment validation (dry run)",
                "dry_run": True,
            }
            return {"execution_log": [log_entry]}

        cwd = _resolve_cwd(settings, state)
        setup_commands = state.get("setup_commands") or []
        build_commands = state.get("build_commands") or []
        test_commands = state.get("test_commands") or []

        # Fallback: if detect_commands was skipped, infer setup from manifest
        if not setup_commands and not build_commands and not test_commands:
            for manifest, cmd in _MANIFEST_SETUP:
                if (cwd / manifest).exists():
                    setup_commands = [cmd]
                    logger.info("env_fallback_setup", manifest=manifest, cmd=cmd)
                    _emit(f"Fallback setup detected from {manifest}: `{cmd}`")
                    break

        phases: list[tuple[str, list[str]]] = [
            ("Setup", setup_commands),
            ("Build", build_commands),
            ("Test", test_commands),
        ]

        for phase_name, commands in phases:
            for cmd in commands:
                _emit(f"Validating {phase_name.lower()}: `{cmd}`")
                success, output = run_project_command(cmd, cwd)
                if not success:
                    msg = f"Baseline {phase_name.lower()} failed (`{cmd}`): {output[:500]}"
                    logger.error(
                        "env_validation_failed",
                        phase=phase_name.lower(),
                        cmd=cmd,
                        output=output[:300],
                    )
                    fail_log: ExecutionLogEntry = {
                        "timestamp": now,
                        "node": NODE_NAME,
                        "message": msg,
                        "dry_run": False,
                    }
                    return {
                        "failure_state": msg,
                        "execution_log": [fail_log],
                    }

        log_entry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"Environment validated — "
                f"{len(setup_commands)} setup, "
                f"{len(build_commands)} build, "
                f"{len(test_commands)} test command(s) passed"
            ),
            "dry_run": False,
        }
        logger.info("env_validated")
        _emit("Environment validation passed")
        return {"execution_log": [log_entry]}

    return validate_environment
