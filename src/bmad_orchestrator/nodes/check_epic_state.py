from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "check_epic_state"


class EpicRoutingDecision(BaseModel):
    decision: Literal["add_to_existing", "create_new"]
    reason: str


def make_check_epic_state_node(
    jira: JiraServiceProtocol,
    claude: ClaudeService,
    settings: Settings,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("pm", settings.bmad_install_dir)

    def check_epic_state(state: OrchestratorState) -> dict[str, Any]:
        team_id = state["team_id"]
        prompt = state["input_prompt"]

        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": NODE_NAME,
            "message": f"Searching for active epics for team '{team_id}'",
            "dry_run": settings.dry_run,
        }

        # Short-circuit: if an epic key was provided via --epic-key, use it directly
        if state["current_epic_id"]:
            log_entry["message"] = f"Using provided epic {state['current_epic_id']}"
            return {
                "current_epic_id": state["current_epic_id"],
                "epic_routing_reason": "epic_key provided explicitly; skipping BMAD routing",
                "execution_log": [log_entry],
            }

        epics = jira.find_epic_by_team(team_id)

        if not epics:
            log_entry["message"] = (
                f"No active epics found for team '{team_id}'; will create new one"
            )
            return {
                "current_epic_id": None,
                "epic_routing_reason": "no active epics found for team; must create new epic",
                "execution_log": [log_entry],
            }

        # Ask Claude (via BMAD PM agent) to decide if the prompt fits an existing epic.
        # This is modeled as a classifier-style decision that MUST return structured JSON.
        epic_summaries = "\n".join(
            f"- {e['key']}: {e['summary']}" for e in epics
        )
        decision = claude.complete_structured(
            system_prompt=system_prompt,
            user_message=(
                "You are executing the BMAD 'Epic Determination' step for the "
                "bmad-create-epics-and-stories workflow.\n\n"
                "We are evaluating whether the following work request fits an existing epic.\n\n"
                f"Work request:\n{prompt}\n\n"
                f"Existing epics for team '{team_id}':\n{epic_summaries}\n\n"
                "Decide whether to:\n"
                "- add_to_existing: attach this work to one of the existing epics\n"
                "- create_new: create a new epic because none of the existing ones fit well\n\n"
                "Return a STRICT JSON object with:\n"
                '{ "decision": "add_to_existing" | "create_new", "reason": "..." }\n'
                "Do not include any extra keys, prose, or markdown."
            ),
            schema=EpicRoutingDecision,
            agent_id="pm",
        )

        if decision.decision == "add_to_existing":
            chosen = epics[0]
            log_entry["message"] = (
                f"Will add to existing epic {chosen['key']} "
                f"(routing_decision_reason={decision.reason})"
            )
            return {
                "current_epic_id": chosen["key"],
                "epic_routing_reason": decision.reason,
                "execution_log": [log_entry],
            }

        log_entry["message"] = (
            "Existing epics do not match; will create new epic "
            f"(routing_decision_reason={decision.reason})"
        )
        return {
            "current_epic_id": None,
            "epic_routing_reason": decision.reason,
            "execution_log": [log_entry],
        }

    return check_epic_state
