from __future__ import annotations

from functools import cached_property
from typing import Any

from jira import JIRA

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.dry_run import skip_if_dry_run
from bmad_orchestrator.utils.jira_adf import description_for_jira_api, description_from_jira_api
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

# Jira Cloud expects Atlassian Document Format (ADF) for ``description``; that only works on
# REST API v3. API v2 rejects ADF with: errors.description = "Operation value must be a string".
_JIRA_REST_OPTIONS: dict[str, Any] = {"rest_api_version": "3"}

_DRY_EPIC: dict[str, Any] = {"key": "DRY-001", "id": "dry-epic-001", "summary": "Dry-run Epic"}
_DRY_STORY: dict[str, Any] = {"key": "DRY-002", "id": "dry-story-002", "summary": "Dry-run Story"}
_DRY_TASK: dict[str, Any] = {"key": "DRY-003", "id": "dry-task-003", "summary": "Dry-run Task"}


def _issue_description_payload(issue: Any) -> Any:
    """Return ``fields.description`` in a form suitable for ``description_from_jira_api``.

    Prefer ``issue.raw['fields']['description']`` (plain JSON dict/str) from the REST response.
    ``issue.fields.description`` is parsed by python-jira into ``PropertyHolder`` objects; using
    that alone forces ``description_from_jira_api`` to fall back to ``str()`` (~56-char repr).
    """
    raw_issue = getattr(issue, "raw", None)
    if isinstance(raw_issue, dict):
        fields_json = raw_issue.get("fields")
        if isinstance(fields_json, dict) and "description" in fields_json:
            return fields_json["description"]
    return getattr(issue.fields, "description", None)


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    """Convert a jira.Issue resource to a plain dict safe for checkpointing."""
    fields = issue.fields
    raw_desc = _issue_description_payload(issue)
    desc_str = description_from_jira_api(raw_desc) if raw_desc is not None else ""
    return {
        "key": issue.key,
        "id": issue.id,
        "summary": fields.summary,
        "description": desc_str,
        "status": fields.status.name if fields.status else None,
        "issue_type": fields.issuetype.name if fields.issuetype else None,
        "labels": list(fields.labels) if fields.labels else [],
        "parent_key": fields.parent.key if getattr(fields, "parent", None) else None,
    }


def _fields_with_adf_description(fields: dict[str, Any]) -> dict[str, Any]:
    """Jira Cloud: description must be ADF; convert markdown strings at the API boundary."""
    out = dict(fields)
    if "description" in out and isinstance(out["description"], str):
        out["description"] = description_for_jira_api(out["description"])
    return out


def _comment_body_for_jira_api(body: str) -> Any:
    """REST API v3 expects comment ``body`` as ADF (same document shape as issue description)."""
    return description_for_jira_api(body)


class JiraService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def _client(self) -> JIRA:
        return JIRA(
            server=self.settings.jira_base_url,
            options=_JIRA_REST_OPTIONS,
            basic_auth=(
                self.settings.jira_username,
                self.settings.jira_api_token.get_secret_value(),
            ),
        )

    def find_epic_by_team(self, team_id: str) -> list[dict[str, Any]]:
        """Return all open Epics in the project (by project key, not label)."""
        jql = (
            f'project = "{self.settings.jira_project_key}" '
            f'AND issuetype = Epic '
            f'AND status != Done '
            f'ORDER BY created DESC'
        )
        issues = self._client.search_issues(jql, maxResults=10)
        return [_issue_to_dict(i) for i in issues]

    @skip_if_dry_run(fake_return=_DRY_EPIC)
    def create_epic(
        self,
        summary: str,
        description: str,
        team_id: str,
    ) -> dict[str, Any]:
        issue = self._client.create_issue(
            fields=_fields_with_adf_description(
                {
                    "project": {"key": self.settings.jira_project_key},
                    "issuetype": {"name": "Epic"},
                    "summary": summary,
                    "description": description,
                    "labels": [team_id],
                }
            )
        )
        logger.info("epic_created", key=issue.key)
        return _issue_to_dict(issue)

    @skip_if_dry_run(fake_return=_DRY_EPIC)
    def update_epic(self, epic_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        fields = _fields_with_adf_description(fields)
        desc = fields.get("description", "")
        desc_len = len(desc) if isinstance(desc, str) else len(str(desc))
        logger.info(
            "jira_epic_update",
            epic_key=epic_key,
            field_keys=list(fields.keys()),
            description_chars=desc_len,
        )
        issue = self._client.issue(epic_key)
        issue.update(fields=fields)
        logger.info("jira_epic_updated", epic_key=epic_key)
        return _issue_to_dict(self._client.issue(epic_key))

    @skip_if_dry_run(fake_return=_DRY_STORY)
    def create_story(
        self,
        epic_key: str,
        summary: str,
        description: str,
        acceptance_criteria: list[str],
        team_id: str,
    ) -> dict[str, Any]:
        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)
        full_description = f"{description}\n\n**Acceptance Criteria:**\n{ac_text}"
        issue = self._client.create_issue(
            fields=_fields_with_adf_description(
                {
                    "project": {"key": self.settings.jira_project_key},
                    "issuetype": {"name": "Story"},
                    "summary": summary,
                    "description": full_description,
                    "labels": [team_id],
                    "parent": {"key": epic_key},
                }
            )
        )
        logger.info("story_created", key=issue.key, epic=epic_key)
        return _issue_to_dict(issue)

    @skip_if_dry_run(fake_return=_DRY_TASK)
    def create_task(
        self,
        story_key: str,
        summary: str,
        description: str,
    ) -> dict[str, Any]:
        issue = self._client.create_issue(
            fields=_fields_with_adf_description(
                {
                    "project": {"key": self.settings.jira_project_key},
                    "issuetype": {"name": "Subtask"},
                    "summary": summary,
                    "description": description,
                    "parent": {"key": story_key},
                }
            )
        )
        logger.info("task_created", key=issue.key, story=story_key)
        return _issue_to_dict(issue)

    def get_epic(self, epic_key: str) -> dict[str, Any] | None:
        """Fetch a single epic by key. Returns None if not found or not an Epic."""
        try:
            issue = self._client.issue(epic_key)
            result = _issue_to_dict(issue)
            if result.get("issue_type") != "Epic":
                logger.warning("not_an_epic", key=epic_key, actual_type=result.get("issue_type"))
                return None
            return result
        except Exception:
            return None

    def get_story(self, story_key: str) -> dict[str, Any] | None:
        try:
            return _issue_to_dict(self._client.issue(story_key))
        except Exception:
            return None

    def list_stories_under_epic(self, epic_key: str) -> list[dict[str, Any]]:
        """Return Story issues whose parent is the given epic (same linkage as create_story)."""
        try:
            jql = (
                f'project = "{self.settings.jira_project_key}" '
                f'AND parent = "{epic_key}" '
                f'AND issuetype = Story'
            )
            issues = self._client.search_issues(jql, maxResults=100)
            return [_issue_to_dict(i) for i in issues]
        except Exception:
            return []

    def get_subtasks(self, story_key: str) -> list[dict[str, Any]]:
        """Return all subtasks of the given story. Empty list if none or on error."""
        try:
            jql = (
                f'project = "{self.settings.jira_project_key}" '
                f'AND parent = "{story_key}" '
                f'AND issuetype = Subtask'
            )
            issues = self._client.search_issues(jql, maxResults=50)
            return [_issue_to_dict(i) for i in issues]
        except Exception:
            return []

    @skip_if_dry_run(fake_return=None)
    def update_story_description(self, story_key: str, description: str) -> None:
        self._client.issue(story_key).update(
            fields=_fields_with_adf_description({"description": description}),
        )

    @skip_if_dry_run(fake_return=None)
    def update_story_summary(self, story_key: str, summary: str) -> None:
        self._client.issue(story_key).update(fields={"summary": summary})

    @skip_if_dry_run(fake_return=None)
    def transition_issue(self, issue_key: str, transition_name: str) -> None:
        issue = self._client.issue(issue_key)
        transitions = self._client.transitions(issue)
        match = next(
            (t for t in transitions if t["name"].lower() == transition_name.lower()),
            None,
        )
        if match:
            self._client.transition_issue(issue, match["id"])
        else:
            logger.warning(
                "transition_not_found",
                issue=issue_key,
                requested=transition_name,
                available=[t["name"] for t in transitions],
            )

    @skip_if_dry_run(fake_return=None)
    def add_comment(self, issue_key: str, body: str) -> str | None:
        """Add a comment to the given Jira issue. Returns the comment id for later updates."""
        # python-jira types body as str; v3 requires ADF dict (see _comment_body_for_jira_api).
        comment = self._client.add_comment(issue_key, _comment_body_for_jira_api(body))
        logger.info("comment_added", issue_key=issue_key)
        return str(comment.id) if comment else None

    @skip_if_dry_run(fake_return=None)
    def update_comment(self, issue_key: str, comment_id: str, body: str) -> None:
        """Update an existing comment's body (e.g. append step notifications)."""
        comment = self._client.comment(issue_key, comment_id)
        comment.update(body=_comment_body_for_jira_api(body))
        logger.info("comment_updated", issue_key=issue_key, comment_id=comment_id)

    @skip_if_dry_run(fake_return=None)
    def set_story_branch_field(self, story_key: str, branch: str) -> None:
        """Store the BMAD git branch in customfield_10145 (BMAD Branch) on the story."""
        self._client.issue(story_key).update(fields={"customfield_10145": branch})
        logger.info("story_branch_field_updated", story_key=story_key, branch=branch)
