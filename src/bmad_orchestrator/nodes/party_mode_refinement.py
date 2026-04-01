from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.create_story_tasks import _parse_acceptance_criteria
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.jira_template import (
    load_template,
    matches_template,
    normalise_jira_headings,
)
from bmad_orchestrator.utils.json_repair import parse_stringified_list
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "party_mode_refinement"


def _summary_matches_user_story_format(summary: str) -> bool:
    """Return True if summary follows 'As a... I want... So that...' format."""
    if not (summary or "").strip():
        return False
    lower = summary.lower()
    return (
        ("as a " in lower or "as an " in lower)
        and " i want " in lower
        and " so that " in lower
    )


class UserStorySummary(BaseModel):
    """Single field for Claude to return a corrected user-story format title."""

    summary: str


class RefinedStory(BaseModel):
    updated_summary: str
    updated_description: str
    acceptance_criteria: list[str] = Field(min_length=1)
    implementation_notes: str = ""

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        """Handle Claude returning acceptance_criteria as a JSON string."""
        return parse_stringified_list(v)


class _SubtaskItem(BaseModel):
    """Single subtask for webhook-generated list (mirrors create_story_tasks.TaskItem)."""

    summary: str
    description: str


class _SubtaskList(BaseModel):
    """List of subtasks to create when story has none (webhook or stories_breakdown)."""

    tasks: list[_SubtaskItem] = Field(min_length=1)

    @field_validator("tasks", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


def make_party_mode_node(
    claude: ClaudeService,
    jira: JiraServiceProtocol,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    designer_prompt = build_system_prompt("designer", settings.bmad_install_dir)
    architect_prompt = build_system_prompt("architect", settings.bmad_install_dir)
    developer_prompt = build_system_prompt("developer", settings.bmad_install_dir)

    def party_mode_refinement(state: OrchestratorState) -> dict[str, Any]:
        prompt = state["input_prompt"]
        project_context = state.get("project_context") or ""
        ctx_block = f"Target project context:\n{project_context}\n\n" if project_context else ""

        now = datetime.now(UTC).isoformat()
        is_webhook = "create_story_tasks" in settings.skip_nodes
        # Jira automation skips create_story_tasks (is_webhook). Epic Generate stories runs it
        # but should still get subtasks from refined output like the Story automation path.
        create_subtasks_after_refinement = (
            is_webhook or settings.execution_mode == "stories_breakdown"
        )

        if settings.execution_mode == "stories_breakdown":
            id_list = [x for x in (state.get("created_story_ids") or []) if x and x != "UNKNOWN"]
            if not id_list and state.get("current_story_id"):
                ck = state["current_story_id"]
                epic_id = state.get("current_epic_id")
                if ck and ck != "UNKNOWN" and ck != epic_id:
                    id_list = [ck]
            if not id_list:
                empty: ExecutionLogEntry = {
                    "timestamp": now,
                    "node": NODE_NAME,
                    "message": (
                        "stories_breakdown: no story keys to refine (created_story_ids empty)"
                    ),
                    "dry_run": settings.dry_run,
                }
                return {"execution_log": [empty]}
            iteration_keys: list[str | None] = list(id_list)
        else:
            iteration_keys = [None]

        all_logs: list[ExecutionLogEntry] = []
        last_architect = ""
        last_developer = ""
        last_content = ""
        last_ac: list[str] = []

        for iter_key in iteration_keys:
            if iter_key is None:
                story_id = state["current_story_id"] or "UNKNOWN"
                story_content = state.get("story_content") or ""
                acceptance_criteria = state.get("acceptance_criteria") or []
            else:
                story_id = iter_key
                story_data = jira.get_story(story_id)
                if not story_data:
                    all_logs.append({
                        "timestamp": now,
                        "node": NODE_NAME,
                        "message": f"party_mode: story {story_id} not found, skipping",
                        "dry_run": settings.dry_run,
                    })
                    continue
                story_content = (story_data.get("description") or "").strip()
                acceptance_criteria = _parse_acceptance_criteria(story_content)

            log_entries: list[ExecutionLogEntry] = []

            # ── Webhook only: ensure story title follows "As a... I want... So that..." ─
            if is_webhook and story_id != "UNKNOWN":
                story_data = jira.get_story(story_id)
                if story_data:
                    current_summary = (story_data.get("summary") or "").strip()
                    if current_summary and not _summary_matches_user_story_format(current_summary):
                        aggregator_prompt_title = build_system_prompt(
                            "scrum_master", settings.bmad_install_dir
                        )
                        corrected = claude.complete_structured(
                            system_prompt=aggregator_prompt_title,
                            user_message=(
                                f"Rewrite this Jira story title into standard user story format: "
                                f'"As a [role], I want [action], so that [benefit]." '
                                f"Keep it one sentence, clear and concise.\n\nCurrent title: {current_summary}"
                            ),
                            schema=UserStorySummary,
                            agent_id="scrum_master",
                            on_event=on_event,
                        )
                        if corrected.summary.strip():
                            jira.update_story_summary(story_id, corrected.summary.strip())
                            log_entries.append({
                                "timestamp": now,
                                "node": NODE_NAME,
                                "message": f"Updated story {story_id} title to user story format (webhook)",
                                "dry_run": settings.dry_run,
                            })

            # ── Designer + Architect reviews (parallel) ─────────────────────────
            ac_text_party = "\n".join(f"- {ac}" for ac in acceptance_criteria)

            def _designer_call(
                sc: str = story_content,
                ac_txt: str = ac_text_party,
                req_prompt: str = prompt,
            ) -> str:
                return claude.complete(
                    system_prompt=designer_prompt,
                    user_message=(
                        "Review the following user story and provide UX/interaction design notes."
                        f"\n\nStory: {sc}\n"
                        f"Acceptance Criteria:\n{ac_txt}"
                        f"\n\nOriginal request: {req_prompt}\n\n"
                        "Provide ALL of the following, but do NOT use numbered lists "
                        "(no '1.', 'a.', 'i.' prefixes). Use short paragraphs or '-' bullets only:\n"
                        "- User flow description\n"
                        "- Edge cases the developer should handle\n"
                        "- Any UX concerns or improvements\n"
                        "Be concise and actionable."
                    ),
                    agent_id="designer",
                    on_event=on_event,
                )

            def _architect_call(
                sc: str = story_content,
                ac_txt: str = ac_text_party,
                ctx: str = ctx_block,
            ) -> str:
                return claude.complete(
                    system_prompt=architect_prompt,
                    user_message=(
                        f"{ctx}"
                        "Review the following user story. "
                        "Provide technical architecture guidance.\n\n"
                        f"Story: {sc}\n"
                        f"Acceptance Criteria:\n{ac_txt}\n\n"
                        "Provide ALL of the following, but do NOT use numbered lists "
                        "(no '1.', 'a.', 'i.' prefixes). Use short paragraphs or '-' bullets only:\n"
                        "- Data model changes needed\n"
                        "- API contracts (if applicable)\n"
                        "- Component/module boundaries\n"
                        "- Technical risks\n"
                        "Be concise and actionable."
                    ),
                    agent_id="architect_party",
                    on_event=on_event,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                designer_future = pool.submit(_designer_call)
                architect_future = pool.submit(_architect_call)
                designer_out = designer_future.result()
                architect_out = architect_future.result()

            log_entries.append({
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Designer (Sally) review complete",
                "dry_run": settings.dry_run,
            })
            log_entries.append({
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Architect (Winston) review complete",
                "dry_run": settings.dry_run,
            })

            # ── Developer review (sequential — depends on both above) ─────────
            developer_out = claude.complete(
                system_prompt=developer_prompt,
                user_message=(
                    f"{ctx_block}"
                    f"Review the story, designer notes, and architect notes. "
                    f"Provide implementation approach and flag ambiguities.\n\n"
                    f"Story: {story_content}\n"
                    f"Designer notes:\n{designer_out}\n"
                    f"Architect notes:\n{architect_out}\n\n"
                    f"Provide ALL of the following, but do NOT use numbered lists "
                    f"(no '1.', 'a.', 'i.' prefixes). Use short paragraphs or '-' bullets only:\n"
                    f"- Implementation approach\n"
                    f"- Files/modules to create or modify\n"
                    f"- Any ambiguities that need clarification\n"
                    f"- Estimated complexity (low/medium/high)\n"
                    f"Be concise and actionable."
                ),
                agent_id="developer_party",
                on_event=on_event,
            )
            log_entries.append({
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Developer (Amelia) review complete",
                "dry_run": settings.dry_run,
            })

            # ── Aggregator: synthesise all three outputs into refined story ──────────
            jira_template = load_template()
            already_template = matches_template(story_content)
            format_note = ""
            if already_template:
                format_note = (
                    "The original story already follows the Jira template format. "
                    "Preserve that structure in updated_description and only refine content.\n\n"
                )
            format_instruction = (
                "updated_description MUST follow the Jira template structure. Use EXACTLY these "
                "section titles in this order, as bold markdown (e.g. **Hypothesis**), never as "
                "numbered/lettered outlines (no '1.', 'a.', 'i.'): "
                "**Hypothesis**, **Intervention**, **Data to Collect**, **Success Threshold**, "
                "**Rationale**, **Designs**, **Mechanics**, **Tracking**, **Acceptance Criteria**. "
                "Use only these bold headings and '-' bullet lists or paragraphs—no outline prefixes."
            )
            if jira_template:
                format_instruction += " Use the reference template below for section order and format."
            aggregator_prompt = build_system_prompt("scrum_master", settings.bmad_install_dir)
            aggregator_user_msg = (
                f"You have received feedback from three experts on this user story. "
                f"Synthesise their feedback into an improved story.\n\n"
                f"{format_note}"
                f"Original story:\n{story_content}\n\n"
                f"UX feedback (Sally):\n{designer_out}\n\n"
                f"Architecture feedback (Winston):\n{architect_out}\n\n"
                f"Developer feedback (Amelia):\n{developer_out}\n\n"
                f"Produce:\n"
                f"- updated_summary: refined one-line story title\n"
                f"- updated_description: improved story body incorporating all feedback. {format_instruction}\n"
                f"- acceptance_criteria: updated, unambiguous list "
                f"(max 8 items — essential, verifiable only)\n"
                f"- implementation_notes: key technical points for the developer (be concise). "
                f"For Jira compatibility: do NOT use numbered or lettered outlines (no '1.', 'a.', 'i.'). "
                f"Use only short paragraphs or simple '-' bullet lists; use **bold** for subsection titles "
                f"if needed, not outline-style headings."
            )
            if jira_template:
                aggregator_user_msg += f"\n\n## Jira template reference:\n{jira_template[:4000]}"
            refined = claude.complete_structured(
                system_prompt=aggregator_prompt,
                user_message=aggregator_user_msg,
                schema=RefinedStory,
                max_tokens=16384,
                agent_id="scrum_master",
                on_event=on_event,
            )
            log_entries.append({
                "timestamp": now,
                "node": NODE_NAME,
                "message": "Aggregator (Bob) synthesised party mode feedback",
                "dry_run": settings.dry_run,
            })

            # ── Update Jira story with aggregated result ──────────────────────────
            # For Jira, we only want the refined story + implementation notes to
            # follow the strict template. Raw expert feedback stays out of the
            # Description field to avoid extra headings/numbered lists.
            enriched_description = (
                f"{refined.updated_description}\n\n"
                f"## Implementation Notes\n{refined.implementation_notes}"
            )
            final_description = normalise_jira_headings(enriched_description)
            jira.update_story_description(story_id, final_description)
            log_entries.append({
                "timestamp": now,
                "node": NODE_NAME,
                "message": f"Updated story {story_id} with aggregated party mode refinements",
                "dry_run": settings.dry_run,
            })

            # ── Webhook / stories_breakdown: create subtasks if story has none ─────
            if create_subtasks_after_refinement and story_id != "UNKNOWN":
                subtasks = jira.get_subtasks(story_id)
                if not subtasks:
                    aggregator_prompt_tasks = build_system_prompt(
                        "scrum_master", settings.bmad_install_dir
                    )
                    sublist = claude.complete_structured(
                        system_prompt=aggregator_prompt_tasks,
                        user_message=(
                            f"From this refined story, produce 2 to 6 concrete subtasks (Jira subtasks) "
                            f"that a developer would implement. Each task: summary (short), description (what to do).\n\n"
                            f"Refined description:\n{refined.updated_description}\n\n"
                            f"Acceptance criteria:\n"
                            + "\n".join(f"- {ac}" for ac in refined.acceptance_criteria)
                            + f"\n\nImplementation notes:\n{refined.implementation_notes or '(none)'}\n\n"
                            f"Return a list of tasks with 'summary' and 'description' for each. "
                            f"Do NOT use numbered or lettered outlines in the text."
                        ),
                        schema=_SubtaskList,
                        agent_id="scrum_master",
                        on_event=on_event,
                    )
                    for task in sublist.tasks:
                        jira.create_task(story_id, task.summary, task.description)
                    log_entries.append({
                        "timestamp": now,
                        "node": NODE_NAME,
                        "message": f"Created {len(sublist.tasks)} subtasks for story {story_id} (webhook)",
                        "dry_run": settings.dry_run,
                    })

            all_logs.extend(log_entries)
            last_architect = architect_out
            last_developer = refined.implementation_notes or developer_out
            last_content = final_description
            last_ac = refined.acceptance_criteria

        return {
            "architect_output": last_architect,
            "developer_output": last_developer,
            "story_content": last_content,
            "acceptance_criteria": last_ac,
            "execution_log": all_logs,
        }

    return party_mode_refinement
