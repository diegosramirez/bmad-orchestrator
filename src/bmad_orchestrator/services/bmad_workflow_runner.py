"""
Invoke BMAD workflows (create-epics-and-stories, correct-course, create-story)
by loading their workflow files and running Claude with that context in headless/YOLO mode.

Output is structured (Pydantic) so the orchestrator can push to Jira.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.utils.jira_template import load_template
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

# Relative to bmad_root (e.g. _bmad/)
PATH_CREATE_EPICS_WORKFLOW = "bmm/workflows/3-solutioning/create-epics-and-stories/workflow.md"
PATH_CREATE_EPICS_STEP01 = (
    "bmm/workflows/3-solutioning/create-epics-and-stories"
    "/steps/step-01-validate-prerequisites.md"
)
PATH_CREATE_EPICS_STEP02 = (
    "bmm/workflows/3-solutioning/create-epics-and-stories"
    "/steps/step-02-design-epics.md"
)
PATH_CORRECT_COURSE_YAML = "bmm/workflows/4-implementation/correct-course/workflow.yaml"
PATH_CORRECT_COURSE_INSTRUCTIONS = "bmm/workflows/4-implementation/correct-course/instructions.md"
PATH_CREATE_STORY_YAML = "bmm/workflows/4-implementation/create-story/workflow.yaml"
PATH_CREATE_STORY_INSTRUCTIONS = "bmm/workflows/4-implementation/create-story/instructions.xml"
PATH_CREATE_STORY_TEMPLATE = "bmm/workflows/4-implementation/create-story/template.md"


def _bmad_path(settings: Settings) -> Path:
    """Resolve BMAD root directory (absolute or relative to CWD)."""
    p = Path(settings.bmad_root)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _read_workflow_text(settings: Settings, rel_path: str) -> str:
    """Read workflow file content; return empty string if missing."""
    root = _bmad_path(settings)
    # bmad_root is "_bmad", so root = cwd/_bmad.
    # PATH_ constants are relative to bmad_root (e.g. bmm/workflows/...),
    # so full = root / rel_path resolves correctly.
    full = root / rel_path
    if not full.exists():
        logger.warning("bmad_workflow_file_missing", path=str(full), rel_path=rel_path)
        return ""
    try:
        return full.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("bmad_workflow_read_error", path=str(full), error=str(e))
        return ""


def load_create_epics_and_stories_context(settings: Settings) -> str:
    """Load BMAD create-epics-and-stories workflow context for headless execution."""
    parts = [
        _read_workflow_text(settings, PATH_CREATE_EPICS_WORKFLOW),
        _read_workflow_text(settings, PATH_CREATE_EPICS_STEP01),
        _read_workflow_text(settings, PATH_CREATE_EPICS_STEP02),
    ]
    combined = "\n\n---\n\n".join(p for p in parts if p.strip())
    if not combined.strip():
        return (
            "BMAD create-epics-and-stories: Create user-value-focused epics. "
            "Produce one epic with concise summary and clear description."
        )
    return combined


def load_correct_course_context(settings: Settings) -> str:
    """Load BMAD correct-course workflow context for headless execution."""
    parts = [
        _read_workflow_text(settings, PATH_CORRECT_COURSE_YAML),
        _read_workflow_text(settings, PATH_CORRECT_COURSE_INSTRUCTIONS),
    ]
    combined = "\n\n---\n\n".join(p for p in parts if p.strip())
    if not combined.strip():
        return (
            "BMAD correct-course: Assess whether an existing epic's description "
            "should be updated to incorporate new work. Propose updated description if needed."
        )
    return combined


def load_create_story_context(settings: Settings) -> str:
    """Load BMAD create-story workflow context for headless execution."""
    parts = [
        _read_workflow_text(settings, PATH_CREATE_STORY_YAML),
        _read_workflow_text(settings, PATH_CREATE_STORY_INSTRUCTIONS),
        _read_workflow_text(settings, PATH_CREATE_STORY_TEMPLATE),
    ]
    combined = "\n\n---\n\n".join(p for p in parts if p.strip())
    if not combined.strip():
        return (
            "BMAD create-story: Create a story with acceptance "
            "criteria, tasks, dependencies, QA scope, and "
            "definition of done. Tasks must be concrete."
        )
    return combined


class BmadWorkflowRunner:
    """
    Runs BMAD workflows in headless/YOLO mode: loads workflow content,
    injects orchestrator context, and returns structured output for Jira.
    """

    def __init__(self, claude: ClaudeService, settings: Settings) -> None:
        self._claude = claude
        self._settings = settings

    def run_create_epics_and_stories(
        self,
        team_id: str,
        prompt: str,
        schema: type[Any],
        jira_template: str = "",
    ) -> Any:
        """Execute BMAD bmad-create-epics-and-stories for a single epic (headless)."""
        if not jira_template:
            jira_template = load_template()
        workflow_context = load_create_epics_and_stories_context(self._settings)
        system_prompt = build_system_prompt("pm", self._settings.bmad_install_dir)
        system_prompt += (
            "\n\nYou are executing the BMAD workflow "
            "'create-epics-and-stories' in HEADLESS/YOLO mode: "
            "no user prompts, no menus. Use the workflow guidance "
            "below only to inform quality. "
            "Return ONLY the requested JSON structure "
            "(summary, description) for ONE epic."
        )
        desc_instruction = (
            "Produce a single Jira Epic: one-line summary and clear description. "
            "The description MUST follow the Jira template: use these section titles in order "
            "as bold markdown (e.g. **Hypothesis**), never as '1.', 'a.', 'i.': "
            "**Hypothesis**, **Intervention**, **Data to Collect**, **Success Threshold**, "
            "**Rationale**, **Designs**, **Mechanics**, **Tracking**, **Acceptance Criteria**. "
            "Use only bold headings and '-' bullet lists or tables."
        )
        user_message = (
            f"## Workflow context (follow its principles):\n{workflow_context}\n\n"
            "## Orchestrator context (your inputs):\n"
            f"- Team: {team_id}\n"
            f"- Work request: {prompt}\n\n"
            f"{desc_instruction} "
            "Return ONLY valid JSON matching the requested schema."
        )
        if jira_template:
            user_message += f"\n\n## Jira template reference:\n{jira_template[:4000]}"
        return self._claude.complete_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            schema=schema,
            agent_id="pm",
        )

    def run_correct_course(
        self,
        existing_epic_id: str,
        existing_desc: str,
        prompt: str,
        schema: type[Any],
    ) -> Any:
        """Execute BMAD bmad-correct-course for epic description update (headless)."""
        workflow_context = load_correct_course_context(self._settings)
        system_prompt = build_system_prompt("pm", self._settings.bmad_install_dir)
        system_prompt += (
            "\n\nYou are executing the BMAD workflow 'correct-course' in HEADLESS/YOLO mode: "
            "no user prompts. Use the workflow guidance below. "
            "Return ONLY the requested JSON structure (needs_update, updated_description, reason)."
        )
        user_message = (
            f"## Workflow context:\n{workflow_context}\n\n"
            "## Orchestrator context:\n"
            f"Existing epic ({existing_epic_id}) description:\n{existing_desc}\n\n"
            f"New work request: {prompt}\n\n"
            "Decide if the epic description should be updated to incorporate this work. "
            "If yes, set needs_update=true and provide full updated_description and reason. "
            "Return ONLY valid JSON matching the requested schema."
        )
        return self._claude.complete_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            schema=schema,
            agent_id="pm",
        )

    def run_create_story(
        self,
        epic_id: str,
        team_id: str,
        prompt: str,
        project_context: str,
        schema: type[Any],
        jira_template: str = "",
    ) -> Any:
        """Execute BMAD create-story workflow (headless). Returns structured story draft."""
        if not jira_template:
            jira_template = load_template()
        workflow_context = load_create_story_context(self._settings)
        system_prompt = build_system_prompt("scrum_master", self._settings.bmad_install_dir)
        system_prompt += (
            "\n\nYou are executing the BMAD workflow 'create-story' in HEADLESS/YOLO mode: "
            "no user prompts, no sprint-status discovery. Use the workflow guidance below. "
            "Return ONLY the requested JSON structure "
            "(summary, description, acceptance_criteria, tasks, "
            "dependencies, qa_scope, definition_of_done). "
            "Tasks must be concrete and implementable."
        )
        ctx_block = (
            f"Target project context:\n{project_context}\n\n" if project_context else ""
        )
        desc_instruction = (
            "Produce a complete user story: summary (As a... I want... so that...), description, "
            "at least 2 concrete acceptance criteria, at least 2 implementable tasks, "
            "dependencies (list), qa_scope (list), definition_of_done (list). "
        )
        if jira_template:
            desc_instruction += (
                "The description MUST follow the Jira template: use these section titles in order "
                "as bold markdown (e.g. **Hypothesis**), never as '1.', 'a.', 'i.': "
                "**Hypothesis**, **Intervention**, **Data to Collect**, **Success Threshold**, "
                "**Rationale**, **Designs**, **Mechanics**, **Tracking**, **Acceptance Criteria**. "
                "Use only bold headings and '-' bullet lists or tables."
            )
        user_message = (
            f"## Workflow context:\n{workflow_context}\n\n"
            f"{ctx_block}"
            "## Orchestrator context:\n"
            f"- Epic: {epic_id}\n"
            f"- Team: {team_id}\n"
            f"- Work request: {prompt}\n\n"
            f"{desc_instruction}"
            "Return ONLY valid JSON matching the requested schema."
        )
        if jira_template:
            user_message += f"\n\n## Jira template reference:\n{jira_template[:4000]}"
        return self._claude.complete_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            schema=schema,
            agent_id="scrum_master",
        )
