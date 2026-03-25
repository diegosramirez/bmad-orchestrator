from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.bmad_workflow_runner import BmadWorkflowRunner
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.jira_template import (
    load_template,
    normalise_jira_headings,
)
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "create_or_correct_epic"


class EpicDraft(BaseModel):
    summary: str
    description: str


class EpicCorrectionDecision(BaseModel):
    needs_update: bool
    updated_description: str = ""
    reason: str = ""


def make_create_or_correct_epic_node(
    jira: JiraServiceProtocol,
    claude: ClaudeService,
    settings: Settings,
    bmad_runner: BmadWorkflowRunner | None = None,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("pm", settings.bmad_install_dir)

    def create_or_correct_epic(state: OrchestratorState) -> dict[str, Any]:
        team_id = state["team_id"]
        prompt = state["input_prompt"]
        existing_epic_id = state["current_epic_id"]

        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": NODE_NAME,
            "message": "",
            "dry_run": settings.dry_run,
        }

        if existing_epic_id:
            existing_epic = jira.get_epic(existing_epic_id)
            existing_desc = (existing_epic or {}).get("description", "")
            if bmad_runner:
                decision = bmad_runner.run_correct_course(
                    existing_epic_id, existing_desc, prompt, EpicCorrectionDecision
                )
            else:
                decision = claude.complete_structured(
                    system_prompt=system_prompt,
                    user_message=(
                        "You are executing the BMAD 'bmad-correct-course' "
                        "workflow for Jira epics.\n\n"
                        "Evaluate whether this existing epic's description "
                        "adequately covers the new work request.\n\n"
                        f"Existing epic ({existing_epic_id}) "
                        f"description:\n{existing_desc}\n\n"
                        f"New work request: {prompt}\n\n"
                        "If the existing description already covers this "
                        "work, set needs_update=false.\n"
                        "If it needs updating, set needs_update=true and "
                        "provide the full updated_description that "
                        "incorporates both the original scope and the "
                        "new work."
                    ),
                    schema=EpicCorrectionDecision,
                    agent_id="pm",
                    on_event=on_event,
                )
            if decision.needs_update and decision.updated_description:
                normalised = normalise_jira_headings(decision.updated_description)
                jira.update_epic(
                    existing_epic_id,
                    {"description": normalised},
                )
                log_entry["message"] = (
                    f"Corrected epic {existing_epic_id}: {decision.reason}"
                )
            else:
                log_entry["message"] = (
                    f"Existing epic {existing_epic_id} is sufficient, "
                    "no update needed"
                )
            return {"current_epic_id": existing_epic_id, "execution_log": [log_entry]}

        jira_template = load_template()
        epic_format_instruction = (
            "Produce a concise epic summary (one line) and a clear description "
            "explaining the problem being solved and the expected outcome."
        )
        if jira_template:
            epic_format_instruction += (
                " The description MUST follow the Jira template: use these section titles in order "
                "as bold markdown (e.g. **Hypothesis**), never as '1.', 'a.', 'i.': "
                "**Hypothesis**, **Intervention**, **Data to Collect**, **Success Threshold**, "
                "**Rationale**, **Designs**, **Mechanics**, **Tracking**, **Acceptance Criteria**. "
                "Use only bold headings and '-' bullet lists or tables."
            )
        if bmad_runner:
            draft = bmad_runner.run_create_epics_and_stories(
                team_id, prompt, EpicDraft, jira_template=jira_template or ""
            )
        else:
            user_msg = (
                "You are executing the BMAD 'bmad-create-epics-and-stories' workflow for this "
                f"team. Create a Jira Epic that will own the stories for this work.\n\n"
                f"Team: {team_id}\n"
                f"Request: {prompt}\n\n"
                f"{epic_format_instruction}"
            )
            if jira_template:
                user_msg += f"\n\nReference template structure:\n{jira_template[:4000]}"
            draft = claude.complete_structured(
                system_prompt=system_prompt,
                user_message=user_msg,
                schema=EpicDraft,
                agent_id="pm",
                on_event=on_event,
            )

        normalised_description = normalise_jira_headings(draft.description)
        epic = jira.create_epic(
            summary=draft.summary[:255],
            description=normalised_description,
            team_id=team_id,
        )
        log_entry["message"] = f"Created epic {epic['key']}: {epic['summary']}"
        return {"current_epic_id": epic["key"], "execution_log": [log_entry]}

    return create_or_correct_epic
