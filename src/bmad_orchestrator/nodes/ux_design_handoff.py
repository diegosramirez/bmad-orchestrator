from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.services.service_factory import build_figma_mcp_config
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.cost_tracking import accumulate_cost
from bmad_orchestrator.utils.json_repair import parse_stringified_list
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "ux_design_handoff"


class ComponentSpec(BaseModel):
    name: str = Field(description="Component name (PascalCase)")
    description: str = Field(description="What the component does and where it appears")
    props: list[str] = Field(default_factory=list, description="Key props or inputs")

    @field_validator("props", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


class UxHandoff(BaseModel):
    summary: str = Field(description="One-paragraph overview of the design")
    components: list[ComponentSpec] = Field(default_factory=list)
    design_tokens: list[str] = Field(
        default_factory=list,
        description="Concrete token values: 'color.primary=#2F5CFF', 'spacing.md=16px', ...",
    )
    accessibility_notes: list[str] = Field(default_factory=list)
    suggested_file_paths: list[str] = Field(default_factory=list)

    @field_validator(
        "components",
        "design_tokens",
        "accessibility_notes",
        "suggested_file_paths",
        mode="before",
    )
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


def format_handoff_markdown(handoff: UxHandoff) -> str:
    lines: list[str] = ["## UX design handoff", "", handoff.summary, ""]

    if handoff.components:
        lines.append("### Components")
        for c in handoff.components:
            lines.append(f"- **{c.name}** — {c.description}")
            if c.props:
                lines.append(f"  - Props: {', '.join(c.props)}")
        lines.append("")

    if handoff.design_tokens:
        lines.append("### Design tokens")
        for t in handoff.design_tokens:
            lines.append(f"- {t}")
        lines.append("")

    if handoff.accessibility_notes:
        lines.append("### Accessibility")
        for a in handoff.accessibility_notes:
            lines.append(f"- {a}")
        lines.append("")

    if handoff.suggested_file_paths:
        lines.append("### Suggested file paths")
        for p in handoff.suggested_file_paths:
            lines.append(f"- `{p}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def make_ux_design_handoff_node(
    agent: ClaudeAgentService,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("designer", settings.bmad_install_dir)

    def ux_design_handoff(state: OrchestratorState) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        figma_url = state.get("figma_url")

        if not figma_url or not settings.figma_mcp_enabled:
            skip_log: ExecutionLogEntry = {
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Skipped — no figma_url or Figma MCP disabled",
                "dry_run": settings.dry_run,
            }
            return {"execution_log": [skip_log]}

        story_content = state.get("story_content") or ""
        acceptance_criteria = state.get("acceptance_criteria") or []
        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)

        prompt = (
            f"Produce a UX design handoff for the developer based on the Figma design "
            f"and the story below. Use the `mcp__figma__*` tools to read the frame, "
            f"components, variables, and layout. Return structured output only.\n\n"
            f"## Figma URL\n{figma_url}\n\n"
            f"## Story\n{story_content}\n\n"
            f"## Acceptance criteria\n{ac_text or '(none)'}\n\n"
            f"Include: a one-paragraph summary, the components to build, concrete "
            f"design-token values (colors, spacing, typography), accessibility notes, "
            f"and suggested file paths."
        )

        result = agent.run_agent(
            prompt,
            system_prompt=system_prompt,
            agent_id="designer",
            mcp_servers=build_figma_mcp_config(settings),
            output_format_schema=UxHandoff,
            max_turns=15,
            on_event=on_event,
        )

        current_cost = state.get("total_cost_usd") or 0.0
        new_cost, budget_msg = accumulate_cost(current_cost, result, settings)

        if result.is_error or result.structured_output is None:
            fail_log: ExecutionLogEntry = {
                "timestamp": now,
                "node": NODE_NAME,
                "message": f"UX handoff failed: {result.result_text or 'no structured output'}",
                "dry_run": settings.dry_run,
            }
            return {
                "total_cost_usd": new_cost,
                "execution_log": [fail_log],
            }

        handoff = result.structured_output
        if not isinstance(handoff, UxHandoff):
            handoff = UxHandoff.model_validate(handoff)
        markdown = format_handoff_markdown(handoff)

        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"UX handoff produced: {len(handoff.components)} components, "
                f"{len(handoff.design_tokens)} tokens"
            ),
            "dry_run": settings.dry_run,
        }
        updates: dict[str, Any] = {
            "ux_handoff": markdown,
            "total_cost_usd": new_cost,
            "execution_log": [log_entry],
        }
        if budget_msg:
            updates["failure_state"] = budget_msg
        return updates

    return ux_design_handoff
