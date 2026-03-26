from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.epic_architect_prompt import EPIC_ARCHITECT_PROMPT_FINAL
from bmad_orchestrator.utils.jira_template import (
    normalise_epic_architect_headings,
    normalise_jira_headings,
)
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "epic_architect"

DISCOVERY_MARKER = "<!-- bmad:discovery -->"
ARCH_HEADING = "## Epic Architect"


class ArchitectureBlockResult(BaseModel):
    """Structured output for Epic Architect (execution_mode epic_architect)."""

    architecture_block: str = Field(
        ...,
        description="Markdown body only; no ## Epic Architect heading.",
    )


def merge_epic_architect_description(existing: str, architecture_block: str) -> str:
    """Insert or replace the ## Epic Architect section; preserve Discovery content above."""
    block = (architecture_block or "").strip()
    new_section = f"{ARCH_HEADING}\n\n{block}"
    text = (existing or "").rstrip()
    if not text:
        return new_section + "\n"

    lines = text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == ARCH_HEADING:
            start_idx = i
            break

    if start_idx is None:
        return text + "\n\n" + new_section + "\n"

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("## ") and stripped != ARCH_HEADING:
            end_idx = j
            break

    prefix = "\n".join(lines[:start_idx]).rstrip()
    suffix = ""
    if end_idx < len(lines):
        suffix = "\n" + "\n".join(lines[end_idx:])
    middle = new_section
    if prefix:
        merged = prefix + "\n\n" + middle + suffix
    else:
        merged = middle + suffix
    return merged.rstrip() + "\n"


def make_epic_architect_node(
    claude: ClaudeService,
    jira: JiraServiceProtocol,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    base_architect = build_system_prompt("architect", settings.bmad_install_dir)
    system_prompt = (
        f"{base_architect}\n\n"
        "You are executing the Epic Architect step in HEADLESS mode: "
        "follow the Epic Architect instructions in the user message exactly. "
        "Return ONLY valid JSON matching the requested schema."
    )

    def epic_architect(state: OrchestratorState) -> dict[str, Any]:
        epic_id = state.get("current_epic_id")
        prompt = state.get("input_prompt") or ""
        project_context = (state.get("project_context") or "").strip()
        ctx_block = f"Target project context:\n{project_context}\n\n" if project_context else ""

        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": NODE_NAME,
            "message": "",
            "dry_run": settings.dry_run,
        }

        if not epic_id:
            log_entry["message"] = "epic_architect: missing current_epic_id (use --epic-key)"
            return {"execution_log": [log_entry]}

        existing = jira.get_epic(epic_id)
        if not existing:
            log_entry["message"] = f"epic_architect: epic {epic_id} not found"
            return {"execution_log": [log_entry]}

        description = (existing.get("description") or "").strip()
        summary = (existing.get("summary") or "").strip()

        if DISCOVERY_MARKER not in description:
            log_entry["message"] = (
                f"epic_architect: epic {epic_id} has no Discovery marker "
                f"({DISCOVERY_MARKER}). Run Discovery on this epic first."
            )
            return {"execution_log": [log_entry]}

        result = claude.complete_structured(
            system_prompt=system_prompt,
            user_message=(
                f"{EPIC_ARCHITECT_PROMPT_FINAL}\n\n"
                f"{ctx_block}"
                "## Orchestrator context\n\n"
                f"- Epic key: {epic_id}\n"
                f"- Work request / prompt: {prompt}\n\n"
                f"- Current summary (title):\n{summary}\n\n"
                f"- Current epic description (Discovery — source of truth):\n{description}\n\n"
                "## JSON output\n"
                "Return ONLY one JSON object with key architecture_block (string)."
            ),
            schema=ArchitectureBlockResult,
            agent_id="architect",
            on_event=on_event,
            max_tokens=32768,
        )

        merged = merge_epic_architect_description(description, result.architecture_block)
        merged = normalise_jira_headings(merged)
        merged = normalise_epic_architect_headings(merged)

        try:
            jira.update_epic(epic_id, {"description": merged})
        except Exception as exc:
            logger.exception("epic_architect_jira_update_failed", epic_key=epic_id, error=str(exc))
            raise

        log_entry["message"] = f"Epic Architect updated description for {epic_id}"
        return {
            "current_epic_id": epic_id,
            "architect_output": result.architecture_block.strip(),
            "execution_log": [log_entry],
        }

    return epic_architect
