from __future__ import annotations

import time
from collections.abc import Callable
from functools import cached_property
from typing import Any, TypeVar

from jira import JIRA

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.dry_run import skip_if_dry_run
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

_DRY_EPIC: dict[str, Any] = {
    "key": "DRY-001", "id": "dry-epic-001", "summary": "Dry-run Epic",
}
_DRY_STORY: dict[str, Any] = {
    "key": "DRY-002", "id": "dry-story-002", "summary": "Dry-run Story",
}
_DRY_TASK: dict[str, Any] = {
    "key": "DRY-003", "id": "dry-task-003", "summary": "Dry-run Task",
}

T = TypeVar("T")


def _is_transient(exc: Exception) -> bool:
    """Return True if the Jira error looks transient (retryable)."""
    msg = str(exc).lower()
    return any(kw in msg for kw in (
        "timeout", "timed out", "connection", "502", "503",
        "504", "429", "rate limit", "ssl", "network",
    ))


def _retry_jira(
    fn: Callable[[], T],
    *,
    label: str = "",
    max_attempts: int = 3,
    delay: float = 2.0,
) -> T:
    """Retry *fn* on transient Jira errors. Re-raise permanent errors."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_transient(exc) and attempt < max_attempts:
                logger.warning(
                    "jira_retry",
                    label=label,
                    attempt=attempt,
                    error=str(exc)[:200],
                )
                time.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]  # unreachable


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    """Convert a jira.Issue resource to a plain dict."""
    fields = issue.fields
    return {
        "key": issue.key,
        "id": issue.id,
        "summary": fields.summary,
        "description": fields.description or "",
        "status": (
            fields.status.name if fields.status else None
        ),
        "issue_type": (
            fields.issuetype.name if fields.issuetype else None
        ),
        "labels": list(fields.labels) if fields.labels else [],
        "parent_key": (
            fields.parent.key
            if getattr(fields, "parent", None)
            else None
        ),
    }


class JiraService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def _client(self) -> JIRA:
        return JIRA(
            server=self.settings.jira_base_url,
            basic_auth=(
                self.settings.jira_username,
                self.settings.jira_api_token.get_secret_value(),
            ),
        )

    def find_epic_by_team(
        self, team_id: str,
    ) -> list[dict[str, Any]]:
        """Return all open Epics in the project."""
        jql = (
            f'project = "{self.settings.jira_project_key}" '
            f"AND issuetype = Epic "
            f"AND status != Done "
            f"ORDER BY created DESC"
        )
        try:
            issues = self._client.search_issues(
                jql, maxResults=10,
            )
            return [_issue_to_dict(i) for i in issues]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "jira_query_failed",
                method="find_epic_by_team",
                error=str(exc)[:200],
            )
            return []

    @skip_if_dry_run(fake_return=_DRY_EPIC)
    def create_epic(
        self,
        summary: str,
        description: str,
        team_id: str,
    ) -> dict[str, Any]:
        issue = _retry_jira(
            lambda: self._client.create_issue(
                fields={
                    "project": {
                        "key": self.settings.jira_project_key,
                    },
                    "issuetype": {"name": "Epic"},
                    "summary": summary,
                    "description": description,
                    "labels": [team_id],
                },
            ),
            label="create_epic",
        )
        logger.info("epic_created", key=issue.key)
        return _issue_to_dict(issue)

    @skip_if_dry_run(fake_return=_DRY_EPIC)
    def update_epic(
        self, epic_key: str, fields: dict[str, Any],
    ) -> dict[str, Any]:
        def _do() -> Any:
            issue = self._client.issue(epic_key)
            issue.update(fields=fields)
            return self._client.issue(epic_key)

        issue = _retry_jira(_do, label="update_epic")
        return _issue_to_dict(issue)

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
        full_desc = (
            f"{description}\n\n"
            f"**Acceptance Criteria:**\n{ac_text}"
        )
        issue = _retry_jira(
            lambda: self._client.create_issue(
                fields={
                    "project": {
                        "key": self.settings.jira_project_key,
                    },
                    "issuetype": {"name": "Story"},
                    "summary": summary,
                    "description": full_desc,
                    "labels": [team_id],
                    "parent": {"key": epic_key},
                },
            ),
            label="create_story",
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
        issue = _retry_jira(
            lambda: self._client.create_issue(
                fields={
                    "project": {
                        "key": self.settings.jira_project_key,
                    },
                    "issuetype": {"name": "Subtask"},
                    "summary": summary,
                    "description": description,
                    "parent": {"key": story_key},
                },
            ),
            label="create_task",
        )
        logger.info("task_created", key=issue.key, story=story_key)
        return _issue_to_dict(issue)

    def get_epic(self, epic_key: str) -> dict[str, Any] | None:
        """Fetch a single epic by key. Returns None on error."""
        try:
            issue = self._client.issue(epic_key)
            result = _issue_to_dict(issue)
            if result.get("issue_type") != "Epic":
                logger.warning(
                    "not_an_epic",
                    key=epic_key,
                    actual_type=result.get("issue_type"),
                )
                return None
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "jira_query_failed",
                method="get_epic",
                key=epic_key,
                error=str(exc)[:200],
            )
            return None

    def get_story(self, story_key: str) -> dict[str, Any] | None:
        try:
            return _issue_to_dict(
                self._client.issue(story_key),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "jira_query_failed",
                method="get_story",
                key=story_key,
                error=str(exc)[:200],
            )
            return None

    def get_subtasks(
        self, story_key: str,
    ) -> list[dict[str, Any]]:
        """Return all subtasks of the given story."""
        try:
            jql = (
                f'project = "{self.settings.jira_project_key}" '
                f'AND parent = "{story_key}" '
                f"AND issuetype = Subtask"
            )
            issues = self._client.search_issues(
                jql, maxResults=50,
            )
            return [_issue_to_dict(i) for i in issues]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "jira_query_failed",
                method="get_subtasks",
                key=story_key,
                error=str(exc)[:200],
            )
            return []

    @skip_if_dry_run(fake_return=None)
    def update_story_description(
        self, story_key: str, description: str,
    ) -> None:
        _retry_jira(
            lambda: self._client.issue(story_key).update(
                fields={"description": description},
            ),
            label="update_story_description",
        )

    @skip_if_dry_run(fake_return=None)
    def update_story_summary(
        self, story_key: str, summary: str,
    ) -> None:
        _retry_jira(
            lambda: self._client.issue(story_key).update(
                fields={"summary": summary},
            ),
            label="update_story_summary",
        )

    @skip_if_dry_run(fake_return=None)
    def transition_issue(
        self, issue_key: str, transition_name: str,
    ) -> None:
        issue = self._client.issue(issue_key)
        transitions = self._client.transitions(issue)
        match = next(
            (
                t
                for t in transitions
                if t["name"].lower() == transition_name.lower()
            ),
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
    def add_comment(
        self, issue_key: str, body: str,
    ) -> str | None:
        """Add a comment to the given Jira issue."""
        comment = _retry_jira(
            lambda: self._client.add_comment(issue_key, body),
            label="add_comment",
        )
        logger.info("comment_added", issue_key=issue_key)
        return str(comment.id) if comment else None

    @skip_if_dry_run(fake_return=None)
    def update_comment(
        self,
        issue_key: str,
        comment_id: str,
        body: str,
    ) -> None:
        """Update an existing comment's body."""
        def _do() -> None:
            c = self._client.comment(issue_key, comment_id)
            c.update(body=body)

        _retry_jira(_do, label="update_comment")
        logger.info(
            "comment_updated",
            issue_key=issue_key,
            comment_id=comment_id,
        )

    @skip_if_dry_run(fake_return=None)
    def set_story_branch_field(
        self, story_key: str, branch: str,
    ) -> None:
        """Store the BMAD git branch in customfield_10145."""
        _retry_jira(
            lambda: self._client.issue(story_key).update(
                fields={"customfield_10145": branch},
            ),
            label="set_story_branch_field",
        )
        logger.info(
            "story_branch_field_updated",
            story_key=story_key,
            branch=branch,
        )
