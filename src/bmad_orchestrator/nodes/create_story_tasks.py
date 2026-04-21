from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.bmad_workflow_runner import BmadWorkflowRunner
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.protocols import JiraServiceProtocol
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.jira_checklist_text import (
    CHECKLIST_TASK_DESCRIPTION_MAX_LEN,
    CHECKLIST_TASK_SUMMARY_MAX_LEN,
    tasks_to_checklist_markdown,
    truncate_checklist_field,
)
from bmad_orchestrator.utils.jira_template import (
    epic_has_discovery_section,
    load_template,
    normalise_jira_headings,
)
from bmad_orchestrator.utils.json_repair import parse_stringified_list
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "create_story_tasks"


def _story_extra_fields_from_epic(
    jira: JiraServiceProtocol,
    settings: Settings,
    epic_key: str,
) -> dict[str, Any] | None:
    """Copy Epic target-repo field onto new Stories when the Epic has a value."""
    cf = jira.get_epic_customfield_10112_value(epic_key)
    if cf is None:
        return None
    return {settings.jira_target_repo_custom_field_id: cf}


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


_CHECKLIST_TASK_FIELD = (
    "Each task is written to Jira Checklist Text as one short row "
    "(bold title + em dash + detail). "
    "Keep it scannable in about two lines in Jira: no paragraphs or exhaustive specs — "
    "put depth in the story description and acceptance criteria instead."
)


class TaskItem(BaseModel):
    summary: str = Field(
        description=(
            f"Short bold label for the checklist row "
            f"(max ~{CHECKLIST_TASK_SUMMARY_MAX_LEN} chars). "
            f"{_CHECKLIST_TASK_FIELD}"
        ),
    )
    description: str = Field(
        description=(
            f"Brief implementable detail (max ~{CHECKLIST_TASK_DESCRIPTION_MAX_LEN} chars). "
            f"{_CHECKLIST_TASK_FIELD}"
        ),
    )

    @field_validator("summary", mode="before")
    @classmethod
    def _truncate_task_summary(cls, v: Any) -> str:
        return truncate_checklist_field(str(v or ""), CHECKLIST_TASK_SUMMARY_MAX_LEN)

    @field_validator("description", mode="before")
    @classmethod
    def _truncate_task_description(cls, v: Any) -> str:
        return truncate_checklist_field(str(v or ""), CHECKLIST_TASK_DESCRIPTION_MAX_LEN)


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


class ContractPlannedStory(BaseModel):
    """Story A: shared interface / contract — no Jira checklist tasks."""

    role: Literal["contract"]
    summary: str = Field(max_length=_JIRA_SUMMARY_MAX)
    description: str
    acceptance_criteria: list[str] = Field(min_length=2)
    spec_kind: str = Field(
        description=(
            "e.g. OpenAPI 3.1, AsyncAPI, GraphQL SDL, protobuf, JSON Schema, event schema"
        ),
    )
    interface_deliverables: list[str] = Field(
        min_length=1,
        description="Concrete paths or locations for the spec (docs/, packages/contracts/, etc.)",
    )
    error_and_auth_expectations: str = Field(
        default="",
        description="Standard errors, auth, idempotency, versioning expectations if applicable.",
    )
    example_fixtures_scope: str = Field(
        default="",
        description="Shared fixtures/examples that align FE/BE without shipping product code.",
    )
    out_of_scope_explicit: list[str] = Field(
        min_length=2,
        description="Explicit exclusions: no SPA, no new HTTP handlers, no migrations, etc.",
    )

    @field_validator(
        "acceptance_criteria",
        "interface_deliverables",
        "out_of_scope_explicit",
        mode="before",
    )
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        return parse_stringified_list(v)


class ImplementationPlannedStory(BaseModel):
    """Frontend or backend story in an epic breakdown batch (optional checklist tasks)."""

    role: Literal["frontend", "backend"]
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


PlannedStoryItem = ImplementationPlannedStory


def _contract_planned_story_description(contract: ContractPlannedStory) -> str:
    """Build Jira description body for a contract story from structured fields."""
    sections: list[str] = [contract.description.strip()]
    sections.append("**Spec kind**\n" + contract.spec_kind.strip())
    sections.append(
        "**Interface deliverables**\n"
        + "\n".join(f"- {d}" for d in contract.interface_deliverables),
    )
    err = contract.error_and_auth_expectations.strip()
    if err:
        sections.append("**Errors / auth / versioning**\n" + err)
    fixtures = contract.example_fixtures_scope.strip()
    if fixtures:
        sections.append("**Example fixtures scope**\n" + fixtures)
    sections.append(
        "**Explicitly out of scope**\n"
        + "\n".join(f"- {x}" for x in contract.out_of_scope_explicit),
    )
    return "\n\n".join(sections)


PlannedBreakdownStory = Annotated[
    ContractPlannedStory | ImplementationPlannedStory,
    Field(discriminator="role"),
]


class EpicStoryBreakdown(BaseModel):
    """One or more user stories for one epic; minimum count unless UI+server scope (Forge).

    When Discovery+Architecture describe both a client app and server-side work, prefer **three**
    stories (shared API contract, then all frontend vs all backend); see _stories_breakdown_create.
    """

    stories: list[PlannedBreakdownStory] = Field(min_length=1)

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
        """Create stories under the epic; default Contract+FE+BE when epic spans UI and server."""
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
        if not epic_has_discovery_section(description):
            log_entry["message"] = (
                f"stories_breakdown: epic {epic_id} has no Discovery section "
                "(expected H1 `# Discovery` in the epic description). "
                "Run Discovery on this epic first."
            )
            return {"execution_log": [log_entry]}

        story_extra = _story_extra_fields_from_epic(jira, settings, epic_id)

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
            "You are breaking down ONE Jira Epic into USER STORIES for BMAD.\n\n"
            "Story count (critical):\n"
            "- Produce the MINIMUM number of stories needed to cover the epic. Do NOT inflate "
            "the count.\n"
            "- **Client + server split (default when applicable):** If Discovery and Epic "
            "Architect together describe BOTH (1) a client-side application or rich web/mobile UI "
            "AND (2) server-side or backend work (not necessarily HTTP: APIs, persistence, jobs, "
            "integrations, etc.), then default to **THREE** stories unless the epic explicitly "
            "demands a single vertical slice, a tiny scope that truly fits one story, or **TWO** "
            "stories when a separate contract story adds no value (e.g. consuming only a frozen "
            "public third-party API with no owned interface to define):\n"
            "  - Story A (**contracts / interface**): **Define the shared contract only** — "
            "the authoritative machine-readable spec of how client and server exchange data: "
            "OpenAPI/AsyncAPI, JSON Schema, GraphQL SDL, protobuf, event schemas, standard error "
            "payloads, auth expectations. Deliverable is a **reviewable interface definition** "
            "(e.g. PR merging spec files under `docs/`, `packages/contracts`, or equivalent). "
            "**No** production UI (no SPA components, pages, routing, styling). **No** server "
            "runtime implementation (no new HTTP handlers, resolvers, ORM entities/migrations, "
            "workers, or deploying backend services). Example mock **fixtures** may be listed "
            "here to align FE/BE. This story is the **single source of truth** for the interface.\n"
            "  - Story B (**frontend**): **All client-side scope** for this epic: UI/UX, "
            "components, SPA routing/state, accessibility, browser storage, client HTTP, "
            "**MSW/mocks/fixtures** "
            "aligned to Story A until the real backend is wired. No server-side implementation: "
            "no new HTTP handlers, resolvers, ORM entities/migrations, workers, or deploying the "
            "backend service as part of this story.\n"
            "  - Story C (**backend**): **All server-side scope** for this epic in "
            "**this product's** backend codebase or deployment unit: HTTP/GraphQL/gRPC handlers, "
            "persistence and "
            "migrations, server business rules, background workers, server auth, integrations. "
            "Deliverable is verifiable **without any SPA** (integration tests, CLI, curl, contract "
            "tests against Story A). Implements and fulfills Story A. No browser or mobile UI "
            "work. In **Intervention**, **Mechanics**, and **Implementation Notes**, list **only** "
            "server-side file paths (e.g. `api/`, `server/`, deploy unit for the API). Do **not** "
            "list SPA paths such as `src/app/`, Angular components, `HttpClient` services, or MSW "
            "— those belong **only** in Story B; Story C may say the SPA consumes this API per "
            "Story A without naming client files.\n"
            "  - **dependencies:** Story B and Story C should list reliance on the agreed "
            "contract from Story A; frontend and backend can proceed **in parallel** once Story A "
            "is stable enough (use dependencies to say \"parallel with mocks\" vs \"blocked on "
            "contract merge\").\n"
            "- **Two stories (fallback):** Use **TWO** stories only when the epic **explicitly** "
            "requires one **vertical slice** (single end-to-end shippable increment) or when "
            "splitting out Story A would be redundant (see above). Then use: **backend** story + "
            "**frontend** story with the same layer rules as Story B/C above; reference the "
            "interface inline in descriptions without a dedicated contract story.\n"
            "- **Single story:** Use ONE story when the epic is genuinely one surface (e.g. only "
            "API change, only CLI, only content) or one small cohesive change with no separate "
            "parallelizable client/server track.\n"
            "- **More than three:** Add a fourth+ story only for clearly separate user outcomes, "
            "release slices, or deliverables that must not ship together — not for micro-layers.\n"
            "- Do NOT add stories for: tests-only work, trivial refactors, or one story per epic "
            "bullet unless each bullet is truly a distinct deliverable.\n\n"
            "Rules:\n"
            "- Do not merge unrelated backend, frontend, and contract work into one giant story "
            "when the epic spans client + server — split as above unless the epic explicitly says "
            "otherwise.\n"
            "- Contract, frontend, and backend stories must each be concrete and completable: "
            "contract story owns **the shared interface artifacts**; backend owns "
            "**every server-side concern** the epic needs; frontend owns **every client-side "
            "concern**, using "
            "mock-backed calls aligned to Story A when needed.\n"
            "- **Database / persistence (default interpretation):** When the epic mentions "
            "database, persistence, storage, or a data layer **without** explicitly stating that "
            "the system of record is **external-only** (e.g. third-party SaaS as sole store, "
            "public API with no owned persistence, vendor DB named as the only backend), assume "
            "**first-party / team-managed** persistence (project-owned database or equivalent "
            "under the team's control) for the **backend** story (Story C). Only plan primary "
            "data around "
            "external or vendor-hosted stores when the epic clearly says so.\n"
            "- **Strict separation (no cross-contamination):**\n"
            "  - In the **contracts** story: do NOT specify or require shipping production UI "
            "or server runtime code — only interface definition, schemas, and optional shared "
            "fixtures.\n"
            "  - In the **backend** story: do NOT describe or require Angular/React/Vue/Svelte, "
            "SPA components, pages, CSS, browser routing, HttpClient, RxJS UI pipelines, "
            "Angular interceptors, MSW in the browser, or any mobile UI toolkit. Acceptance is "
            "verifiable against **running server-side behavior** and conformance to Story A — "
            "not by shipping a SPA. Do **not** paste client file trees (e.g. `src/app/services/`) "
            "or frontend service class names as deliverables of this story.\n"
            "  - In the **frontend** story: do NOT describe implementing server-side code: HTTP "
            "or GraphQL handlers, resolvers, ORM/DB migrations, background workers, server-side "
            "auth middleware, or deploying the backend as part of this story. The frontend may "
            "define TypeScript types and client modules that **call** the backend or mocks; it "
            "must not own server implementation.\n"
            "  - **Interface ownership:** The full interface spec lives in the **contracts** "
            "story; frontend and backend stories **reference** Story A (paths, version) rather "
            "than duplicating "
            "the entire spec in prose.\n"
            "  - **No duplicate client layer:** SPA HTTP client code, framework services "
            "(e.g. Angular HttpClient wrappers), and browser mocks appear **only** in the "
            "frontend story — not in the backend or contracts story summaries.\n"
            "- Do NOT micro-split beyond that (e.g. one story per minor layer) without clear "
            "boundaries — fewer clearer stories beat noisy fragmentation.\n"
            "- Stories must be mutually distinct; together they should cover the epic scope "
            "implied by Discovery and Epic Architect below.\n"
            "- Do NOT propose a story whose summary is essentially the same as an EXISTING "
            "story summary listed below (same intent).\n"
            "- Each story: summary as 'As a ... I want ... so that ...', concrete description, "
            "at least 2 acceptance criteria.\n"
            "- **JSON shape (required):** Every object in the `stories` array MUST include "
            '`"role"`: `"contract"` | `"frontend"` | `"backend"`.\n'
            "  - **Story A (contracts / interface):** set `\"role\": \"contract\"`. Include "
            "`summary`, `description`, `acceptance_criteria` (min 2), `spec_kind` (e.g. OpenAPI "
            "3.1), `interface_deliverables` (non-empty list of concrete spec paths/locations), "
            "`error_and_auth_expectations` (string, may be empty), `example_fixtures_scope` "
            "(string, may be empty), `out_of_scope_explicit` (min 2 bullets: no SPA, no server "
            "runtime, etc.). Do **NOT** include a `tasks` field — contract stories never use "
            "Jira Checklist Text.\n"
            "  - **Story B (frontend) and Story C (backend):** set `\"role\": \"frontend\"` or "
            '`"role\": \"backend\"` respectively. Same fields as before: `summary`, '
            "`description`, `acceptance_criteria`, optional `tasks`, `dependencies`, `qa_scope`, "
            "`definition_of_done`.\n"
            "- For **frontend** and **backend** only: `tasks` are optional; include only when "
            "they add value (concrete sub-steps).\n"
            "- If you include tasks on a frontend/backend story: each is for Jira Checklist Text "
            "— a short bold title (summary) plus one brief phrase (description); readable in "
            "~2 lines in Jira, not a paragraph. Put depth in the story description and ACs.\n"
            f"{format_note}"
            f"- Epic key: {epic_id}\n"
            f"- Team: {team_id}\n"
            f"- Orchestrator prompt context: {prompt}\n\n"
            "## EXISTING stories under this epic (do not duplicate):\n"
            f"{existing_summaries_text or '(none)'}\n\n"
            "## Epic description (source of truth — includes Discovery and Epic Architect):\n"
            f"{description[:24000]}\n\n"
            "Return JSON matching the EpicStoryBreakdown schema: a `stories` array where each "
            "element includes `role` and all fields required for that role (`contract` vs "
            "`frontend`/`backend`), as described above."
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

            if isinstance(planned, ContractPlannedStory):
                body = normalise_jira_headings(_contract_planned_story_description(planned))
            else:
                body = normalise_jira_headings(planned.description)
            story = jira.create_story(
                epic_key=epic_id,
                summary=planned.summary[:_JIRA_SUMMARY_MAX],
                description=body,
                acceptance_criteria=planned.acceptance_criteria,
                team_id=team_id,
                extra_fields=story_extra,
            )
            key = str(story["key"])
            created_keys.append(key)
            existing_keys.add(norm)

            if isinstance(planned, ImplementationPlannedStory) and planned.tasks:
                jira.set_story_checklist_text(
                    key,
                    tasks_to_checklist_markdown(planned.tasks),
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
        ctx_block = (
            f"Target project context:\n{project_context}\n\n" if project_context else ""
        )
        if bmad_runner:
            draft = bmad_runner.run_create_story(
                epic_id, team_id, prompt, project_context, StoryDraft,
                jira_template=jira_template or "",
            )
        else:
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
                "- Tasks populate Jira Checklist Text: each has a short `summary` (bold title) and "
                "a brief `description` (one short phrase). The whole row must stay scannable in "
                "~2 lines — no multi-sentence paragraphs; details belong in the story and ACs.\n"
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
                "- Tasks are specific, implementable engineering steps (no fuzzy labels) and each "
                "is short enough for a compact Jira checklist line.\n"
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
                    "- Specific, implementable tasks (each kept short for Jira Checklist Text)\n"
                    "- Clear dependencies, QA scope, and Definition of Done"
                ),
                schema=StoryDraft,
                agent_id="scrum_master",
                max_tokens=32768,
                on_event=on_event,
            )

        single_story_extra = (
            _story_extra_fields_from_epic(jira, settings, epic_id)
            if epic_id != "UNKNOWN"
            else None
        )
        story = jira.create_story(
            epic_key=epic_id,
            summary=draft.summary[:_JIRA_SUMMARY_MAX],
            description=draft.description,
            acceptance_criteria=draft.acceptance_criteria,
            team_id=team_id,
            extra_fields=single_story_extra,
        )

        if draft.tasks:
            jira.set_story_checklist_text(
                story["key"],
                tasks_to_checklist_markdown(draft.tasks),
            )

        log_entry["message"] = (
            f"Created story {story['key']} with {len(draft.tasks)} tasks in Checklist Text "
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
