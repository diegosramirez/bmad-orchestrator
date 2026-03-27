from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.epic_architect import DISCOVERY_MARKER
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.bmad_workflow_runner import BmadWorkflowRunner
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.jira_template import load_template, normalise_jira_headings
from bmad_orchestrator.utils.json_repair import parse_stringified_list
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "create_story_tasks"


def _parse_acceptance_criteria(description: str) -> list[str]:
    """Extract acceptance criteria from a Jira story description.

    The orchestrator stores AC in the format:
        **Acceptance Criteria:**
        - criterion 1
        - criterion 2
    """
    marker = "**Acceptance Criteria:**"
    idx = description.find(marker)
    if idx == -1:
        return []
    after = description[idx + len(marker) :]
    criteria = []
    for line in after.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            criteria.append(stripped[2:])
        elif stripped and criteria:
            # Non-bullet line after we started collecting → stop
            break
    return criteria


class TaskItem(BaseModel):
    summary: str
    description: str


_JIRA_SUMMARY_MAX = 255


class StoryDraft(BaseModel):
    summary: str = Field(
        max_length=_JIRA_SUMMARY_MAX,
        description="Jira story summary. Must be under 255 characters.",
    )
    description: str
    acceptance_criteria: list[str] = Field(min_length=2)
    tasks: list[TaskItem] = Field(min_length=2)
    dependencies: list[str] = Field(
        default_factory=list,
        description="Key technical or organizational dependencies for this story.",
    )
    qa_scope: list[str] = Field(
        default_factory=list,
        description="What will be covered by QA for this story.",
    )
    definition_of_done: list[str] = Field(
        default_factory=list,
        description="Concrete Definition of Done checklist items for this story.",
    )

    @field_validator(
        "acceptance_criteria",
        "tasks",
        "dependencies",
        "qa_scope",
        "definition_of_done",
        mode="before",
    )
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        """Handle Claude returning list fields as JSON strings."""
        return parse_stringified_list(v)


def _normalize_story_summary(summary: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for dedupe keys."""
    s = (summary or "").strip().lower()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


class PlannedStoryItem(BaseModel):
    """One story in an epic breakdown batch (tasks optional)."""

    summary: str = Field(max_length=_JIRA_SUMMARY_MAX)
    description: str
    acceptance_criteria: list[str] = Field(min_length=2)
    tasks: list[TaskItem] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    qa_scope: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)

    @field_validator(
        "acceptance_criteria",
        "tasks",
        "dependencies",
        "qa_scope",
        "definition_of_done",
        mode="before",
    )
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


class EpicStoryBreakdown(BaseModel):
    """Multiple user stories covering one epic (Forge stories_breakdown mode)."""

    stories: list[PlannedStoryItem] = Field(min_length=1)

    @field_validator("stories", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


def make_create_story_tasks_node(
    jira: JiraServiceProtocol,
    claude: ClaudeService,
    settings: Settings,
    bmad_runner: BmadWorkflowRunner | None = None,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("scrum_master", settings.bmad_install_dir)

    def _stories_breakdown_create(state: OrchestratorState) -> dict[str, Any]:
        """Create N stories under the epic from epic description (Discovery + Architect)."""
        team_id = state["team_id"]
        prompt = state["input_prompt"]
        epic_id = state.get("current_epic_id")
        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": NODE_NAME,
            "message": "",
            "dry_run": settings.dry_run,
        }
        if not epic_id or epic_id == "UNKNOWN":
            log_entry["message"] = "stories_breakdown: missing current_epic_id (use --epic-key)"
            return {"execution_log": [log_entry]}

        epic = jira.get_epic(epic_id)
        if not epic:
            log_entry["message"] = f"stories_breakdown: epic {epic_id} not found"
            return {"execution_log": [log_entry]}

        description = (epic.get("description") or "").strip()
        if DISCOVERY_MARKER not in description:
            log_entry["message"] = (
                f"stories_breakdown: epic {epic_id} has no Discovery marker "
                f"({DISCOVERY_MARKER}). Run Discovery on this epic first."
            )
            return {"execution_log": [log_entry]}

        existing_issues = jira.list_stories_under_epic(epic_id)
        existing_keys = {
            _normalize_story_summary(str(x.get("summary") or "")) for x in existing_issues
        }
        existing_keys.discard("")

        jira_template = load_template()
        ctx_block = (
            f"Target project context:\n{(state.get('project_context') or '').strip()}\n\n"
            if (state.get("project_context") or "").strip()
            else ""
        )
        existing_summaries_text = "\n".join(
            f"- {x.get('summary', '')}" for x in existing_issues[:50]
        )
        format_note = ""
        if jira_template:
            format_note = (
                "Each story description MUST follow the Jira template section order as bold "
                "markdown (**Hypothesis**, **Intervention**, etc.) like other BMAD stories.\n\n"
            )
        user_msg = (
            f"{ctx_block}"
            "You are breaking down ONE Jira Epic into multiple USER STORIES for BMAD.\n\n"
            "Rules:\n"
            "- Each story must be a vertical, end-to-end slice one agent can implement (not "
            "separate frontend-only / backend-only tickets).\n"
            "- Stories must be mutually distinct; together they should cover the epic scope "
            "implied by Discovery and Epic Architect below.\n"
            "- Do NOT propose a story whose summary is essentially the same as an EXISTING "
            "story summary listed below (same intent).\n"
            "- Each story: summary as 'As a ... I want ... so that ...', concrete description, "
            "at least 2 acceptance criteria.\n"
            "- Tasks are optional; include only when they add value (concrete sub-steps).\n"
            f"{format_note}"
            f"- Epic key: {epic_id}\n"
            f"- Team: {team_id}\n"
            f"- Orchestrator prompt context: {prompt}\n\n"
            "## EXISTING stories under this epic (do not duplicate):\n"
            f"{existing_summaries_text or '(none)'}\n\n"
            "## Epic description (source of truth — includes Discovery and Epic Architect):\n"
            f"{description[:24000]}\n\n"
            "Return JSON matching the EpicStoryBreakdown schema (field: stories array)."
        )
        if jira_template:
            user_msg += f"\n\n## Jira template reference:\n{jira_template[:4000]}"

        breakdown = claude.complete_structured(
            system_prompt=system_prompt,
            user_message=user_msg,
            schema=EpicStoryBreakdown,
            agent_id="scrum_master",
            max_tokens=32768,
            on_event=on_event,
        )

        seen_in_batch: set[str] = set()
        created_keys: list[str] = []
        skipped: list[str] = []

        for planned in breakdown.stories:
            norm = _normalize_story_summary(planned.summary)
            if not norm:
                continue
            if norm in existing_keys or norm in seen_in_batch:
                skipped.append(planned.summary[:80])
                continue
            seen_in_batch.add(norm)

            body = normalise_jira_headings(planned.description)
            story = jira.create_story(
                epic_key=epic_id,
                summary=planned.summary[:_JIRA_SUMMARY_MAX],
                description=body,
                acceptance_criteria=planned.acceptance_criteria,
                team_id=team_id,
            )
            key = str(story["key"])
            created_keys.append(key)
            existing_keys.add(norm)

            for task in planned.tasks:
                jira.create_task(
                    story_key=key,
                    summary=task.summary[:_JIRA_SUMMARY_MAX],
                    description=task.description,
                )

        if not created_keys:
            log_entry["message"] = (
                "stories_breakdown: no new stories created "
                f"(duplicates skipped or empty plan). Skipped hints: {skipped[:5]}"
            )
            return {"execution_log": [log_entry]}

        last_key = created_keys[-1]
        last_story = jira.get_story(last_key)
        last_desc = (last_story or {}).get("description") or ""
        last_ac = _parse_acceptance_criteria(last_desc)

        log_entry["message"] = (
            f"stories_breakdown: created {len(created_keys)} story/stories under {epic_id}: "
            f"{', '.join(created_keys)}"
        )
        return {
            "current_story_id": last_key,
            "created_story_ids": created_keys,
            "story_content": last_desc,
            "acceptance_criteria": last_ac,
            "dependencies": [],
            "qa_scope": [],
            "definition_of_done": [],
            "execution_log": [log_entry],
        }

    def create_story_tasks(state: OrchestratorState) -> dict[str, Any]:
        if settings.execution_mode == "stories_breakdown":
            return _stories_breakdown_create(state)

        team_id = state["team_id"]
        prompt = state["input_prompt"]
        epic_id = state["current_epic_id"] or "UNKNOWN"
        existing_story_id = state["current_story_id"]

        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": NODE_NAME,
            "message": "",
            "dry_run": settings.dry_run,
        }

        # Idempotency: if story already exists, reload and skip creation
        if existing_story_id:
            story = jira.get_story(existing_story_id)
            if story:
                log_entry["message"] = f"Story {existing_story_id} already exists, reusing"
                desc = story["description"] or ""
                ac = _parse_acceptance_criteria(desc)
                return {
                    "current_story_id": existing_story_id,
                    "story_content": desc,
                    "acceptance_criteria": ac,
                    "dependencies": [],
                    "qa_scope": [],
                    "definition_of_done": [],
                    "execution_log": [log_entry],
                }

        project_context = state.get("project_context") or ""
        jira_template = load_template()
        story_format_instruction = (
            "- Description must explain the context and implementation constraints\n"
        )
        if jira_template:
            story_format_instruction += (
                "- Description MUST follow the Jira template: use these section titles in order "
                "as bold markdown (e.g. **Hypothesis**), never as '1.', 'a.', 'i.': "
                "**Hypothesis**, **Intervention**, **Data to Collect**, **Success Threshold**, "
                "**Rationale**, **Designs**, **Mechanics**, **Tracking**, **Acceptance Criteria**. "
                "Use only bold headings and '-' bullet lists or tables.\n"
            )

        # Primary BMAD `/bmad-create-story`: use workflow runner if available, else inline prompt.
        if bmad_runner:
            draft = bmad_runner.run_create_story(
                epic_id, team_id, prompt, project_context, StoryDraft,
                jira_template=jira_template or "",
            )
        else:
            ctx_block = (
                f"Target project context:\n{project_context}\n\n" if project_context else ""
            )
            user_msg = (
                f"{ctx_block}"
                "You are executing the BMAD `/bmad-create-story` workflow for this team.\n"
                "Create a well-formed user story for the following work request.\n\n"
                f"Epic: {epic_id}\n"
                f"Team: {team_id}\n"
                f"Request: {prompt}\n\n"
                "Requirements:\n"
                "- Summary must be a single 'As a ... I want ... so that ...' sentence\n"
                f"{story_format_instruction}"
                "- Acceptance criteria must be concrete and verifiable (INVEST criteria)\n"
                "- Tasks must be specific, implementable steps (not vague categories)\n"
                "- Dependencies must list any upstream systems, teams, or prerequisites\n"
                "- QA scope must clearly describe what will be tested and how\n"
                "- Definition of Done must be a concrete checklist the team can tick off\n"
                "- Produce at least 2 acceptance criteria and at least 2 tasks"
            )
            if jira_template:
                user_msg += f"\n\nJira template reference:\n{jira_template[:4000]}"
            draft = claude.complete_structured(
                system_prompt=system_prompt,
                user_message=user_msg,
                schema=StoryDraft,
                agent_id="scrum_master",
                max_tokens=32768,
                on_event=on_event,
            )

        # Normalise description headings to avoid 1./a./i. outlines in Jira.
        draft.description = normalise_jira_headings(draft.description)

        # Quality gate: validate that the story is concrete and implementable. If the
        # acceptance criteria or tasks are vague, ask BMAD to refine the story once.
        class StoryQualityAssessment(BaseModel):
            is_clear: bool
            issues: list[str]

        ac_text = "\n- ".join(draft.acceptance_criteria)
        task_lines = [f"{t.summary}: {t.description}" for t in draft.tasks]
        tasks_text = "\n- ".join(task_lines)

        quality = claude.complete_structured(
            system_prompt=system_prompt,
            user_message=(
                "You are acting as a BMAD Scrum Master performing a quality gate on a "
                "newly proposed story from `/bmad-create-story`.\n\n"
                "Assess whether:\n"
                "- Acceptance criteria are concrete, testable, and not vague.\n"
                "- Tasks are specific, implementable engineering steps (no fuzzy labels).\n"
                "- Dependencies, QA scope, and Definition of Done are present and actionable.\n\n"
                "Return a STRICT JSON object with:\n"
                '{ "is_clear": true | false, "issues": ["..."] }\n\n'
                "Story details to review:\n"
                f"Summary: {draft.summary}\n\n"
                f"Description:\n{draft.description}\n\n"
                f"Acceptance criteria:\n- {ac_text}\n\nTasks:\n- {tasks_text}"
            ),
            schema=StoryQualityAssessment,
            agent_id="scrum_master",
            on_event=on_event,
        )

        if not quality.is_clear:
            refinement_instructions = "\n".join(f"- {issue}" for issue in quality.issues) or (
                "- Make acceptance criteria and tasks more concrete and implementable."
            )
            draft = claude.complete_structured(
                system_prompt=system_prompt,
                user_message=(
                    f"{ctx_block}"
                    "Refine the following story produced by `/bmad-create-story` so that it "
                    "passes the BMAD quality gate.\n\n"
                    "Current story:\n"
                    f"Summary: {draft.summary}\n\n"
                    f"Description:\n{draft.description}\n\n"
                    "Acceptance criteria:\n- "
                    + "\n- ".join(draft.acceptance_criteria)
                    + "\n\nTasks:\n- "
                    + "\n- ".join(
                        f"{task.summary}: {task.description}"
                        for task in draft.tasks
                    )
                    + "\n\nDependencies:\n- "
                    + ("\n- ".join(draft.dependencies) or "(none listed)")
                    + "\n\nQA scope:\n- "
                    + ("\n- ".join(draft.qa_scope) or "(none listed)")
                    + "\n\nDefinition of Done:\n- "
                    + ("\n- ".join(draft.definition_of_done) or "(none listed)")
                    + "\n\nQuality issues to fix:\n"
                    f"{refinement_instructions}\n\n"
                    "Return ONLY a corrected story in the same structured format "
                    "you used before, with:\n"
                    "- Concrete, testable acceptance criteria\n"
                    "- Specific, implementable tasks\n"
                    "- Clear dependencies, QA scope, and Definition of Done"
                ),
                schema=StoryDraft,
                agent_id="scrum_master",
                max_tokens=32768,
                on_event=on_event,
            )

        story = jira.create_story(
            epic_key=epic_id,
            summary=draft.summary[:_JIRA_SUMMARY_MAX],
            description=draft.description,
            acceptance_criteria=draft.acceptance_criteria,
            team_id=team_id,
        )

        for task in draft.tasks:
            jira.create_task(
                story_key=story["key"],
                summary=task.summary[:_JIRA_SUMMARY_MAX],
                description=task.description,
            )

        log_entry["message"] = (
            f"Created story {story['key']} with {len(draft.tasks)} tasks "
            f"and {len(draft.acceptance_criteria)} ACs"
        )

        return {
            "current_story_id": story["key"],
            "story_content": draft.description,
            "acceptance_criteria": draft.acceptance_criteria,
            "dependencies": draft.dependencies,
            "qa_scope": draft.qa_scope,
            "definition_of_done": draft.definition_of_done,
            "execution_log": [log_entry],
        }

    return create_story_tasks
