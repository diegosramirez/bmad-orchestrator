"""Parse Jira webhook POST body into run context (team_id, story_key, epic_key, prompt)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JiraWebhookContext:
    """Extracted context from a Jira issue webhook payload."""

    team_id: str
    story_key: str
    epic_key: str | None
    prompt: str


def parse_jira_webhook(body: dict[str, Any]) -> JiraWebhookContext | None:
    """
    Parse a Jira webhook POST body and return run context.

    Returns None if required fields are missing (issue, issue.fields, issue.key,
    issue.fields.project.key).
    """
    try:
        issue = body.get("issue")
        if not issue or not isinstance(issue, dict):
            return None
        fields = issue.get("fields")
        if not fields or not isinstance(fields, dict):
            return None
        story_key = issue.get("key")
        if not story_key or not isinstance(story_key, str):
            return None
        project = fields.get("project")
        if not project or not isinstance(project, dict):
            return None
        team_id = project.get("key")
        if not team_id or not isinstance(team_id, str):
            return None
        parent = fields.get("parent")
        epic_key: str | None = None
        if parent and isinstance(parent, dict):
            epic_key = parent.get("key") or None
            if epic_key is not None and not isinstance(epic_key, str):
                epic_key = None
        summary = fields.get("summary")
        prompt = summary if isinstance(summary, str) and summary.strip() else story_key
        return JiraWebhookContext(
            team_id=team_id,
            story_key=story_key,
            epic_key=epic_key,
            prompt=prompt.strip() if isinstance(prompt, str) else story_key,
        )
    except (TypeError, AttributeError, KeyError):
        return None
