from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

_PROJECT_PREFIX = "DUMMY"

_SUBDIR_FILE_PREFIX: dict[str, str] = {
    "epics": "EPIC_",
    "stories": "USER_STORY_",
    "tasks": "TASK_",
}


class DummyJiraService:
    """File-backed Jira service that reads/writes markdown files with YAML frontmatter."""

    def __init__(self, settings: Settings, base_dir: Path | None = None) -> None:
        self.settings = settings
        self._base = base_dir or Path(settings.dummy_data_dir).expanduser() / "jira"
        for subdir in ("epics", "stories", "tasks"):
            (self._base / subdir).mkdir(parents=True, exist_ok=True)

    # ── Key generation ────────────────────────────────────────────────────────

    def _next_key(self) -> str:
        counter_file = self._base / "_counter.json"
        if counter_file.exists():
            data = json.loads(counter_file.read_text())
        else:
            data = {"next_id": 1}
        key_num = data["next_id"]
        data["next_id"] = key_num + 1
        counter_file.write_text(json.dumps(data))
        return f"{_PROJECT_PREFIX}-{key_num}"

    # ── File I/O helpers ──────────────────────────────────────────────────────

    def _write_issue(self, subdir: str, issue_dict: dict[str, Any]) -> None:
        prefix = _SUBDIR_FILE_PREFIX.get(subdir, "")
        path = self._base / subdir / f"{prefix}{issue_dict['key']}.md"
        frontmatter = yaml.dump(issue_dict, default_flow_style=False, sort_keys=False)
        desc = issue_dict.get("description", "")
        body = f"# {issue_dict['key']}: {issue_dict['summary']}\n\n{desc}"
        path.write_text(f"---\n{frontmatter}---\n\n{body}\n")
        logger.info("dummy_jira_write", path=str(path), key=issue_dict["key"])

    def _read_issue(self, subdir: str, key: str) -> dict[str, Any] | None:
        prefix = _SUBDIR_FILE_PREFIX.get(subdir, "")
        path = self._base / subdir / f"{prefix}{key}.md"
        if not path.exists():
            return None
        text = path.read_text()
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None
        return yaml.safe_load(parts[1])

    def _read_all_in(self, subdir: str) -> list[dict[str, Any]]:
        results = []
        for md_file in sorted((self._base / subdir).glob("*.md")):
            text = md_file.read_text()
            parts = text.split("---", 2)
            if len(parts) >= 3:
                data = yaml.safe_load(parts[1])
                if data:
                    results.append(data)
        return results

    def _make_issue_dict(
        self,
        key: str,
        summary: str,
        description: str,
        issue_type: str,
        labels: list[str],
        parent_key: str | None = None,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "id": f"dummy-{key.lower()}",
            "summary": summary,
            "description": description,
            "status": "Open",
            "issue_type": issue_type,
            "labels": labels,
            "parent_key": parent_key,
            "created_at": datetime.now(UTC).isoformat(),
        }

    # ── Public API (matches JiraServiceProtocol) ──────────────────────────────

    def find_epic_by_team(self, team_id: str) -> list[dict[str, Any]]:
        all_epics = self._read_all_in("epics")
        return [
            e for e in all_epics
            if e.get("status") != "Done" and team_id in (e.get("labels") or [])
        ]

    def create_epic(self, summary: str, description: str, team_id: str) -> dict[str, Any]:
        key = self._next_key()
        issue = self._make_issue_dict(key, summary, description, "Epic", [team_id])
        self._write_issue("epics", issue)
        logger.info("dummy_epic_created", key=key)
        return issue

    def update_epic(self, epic_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        issue = self._read_issue("epics", epic_key)
        if issue is None:
            msg = f"Epic {epic_key} not found in dummy store"
            raise ValueError(msg)
        issue.update(fields)
        self._write_issue("epics", issue)
        return issue

    def create_story(
        self,
        epic_key: str,
        summary: str,
        description: str,
        acceptance_criteria: list[str],
        team_id: str,
    ) -> dict[str, Any]:
        key = self._next_key()
        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)
        full_description = f"{description}\n\n**Acceptance Criteria:**\n{ac_text}"
        issue = self._make_issue_dict(
            key, summary, full_description, "Story", [team_id], parent_key=epic_key
        )
        self._write_issue("stories", issue)
        logger.info("dummy_story_created", key=key, epic=epic_key)
        return issue

    def create_task(self, story_key: str, summary: str, description: str) -> dict[str, Any]:
        key = self._next_key()
        issue = self._make_issue_dict(
            key, summary, description, "Sub-task", [], parent_key=story_key
        )
        self._write_issue("tasks", issue)
        logger.info("dummy_task_created", key=key, story=story_key)
        return issue

    def get_epic(self, epic_key: str) -> dict[str, Any] | None:
        issue = self._read_issue("epics", epic_key)
        if issue and issue.get("issue_type") != "Epic":
            return None
        return issue

    def get_story(self, story_key: str) -> dict[str, Any] | None:
        return self._read_issue("stories", story_key)

    def get_subtasks(self, story_key: str) -> list[dict[str, Any]]:
        """Return all subtasks of the given story."""
        all_tasks = self._read_all_in("tasks")
        return [t for t in all_tasks if t.get("parent_key") == story_key]

    def update_story_description(self, story_key: str, description: str) -> None:
        issue = self._read_issue("stories", story_key)
        if issue:
            issue["description"] = description
            self._write_issue("stories", issue)

    def update_story_summary(self, story_key: str, summary: str) -> None:
        issue = self._read_issue("stories", story_key)
        if issue:
            issue["summary"] = summary
            self._write_issue("stories", issue)

    def transition_issue(self, issue_key: str, transition_name: str) -> None:
        for subdir in ("epics", "stories", "tasks"):
            issue = self._read_issue(subdir, issue_key)
            if issue:
                issue["status"] = transition_name.title()
                self._write_issue(subdir, issue)
                logger.info("dummy_transition", key=issue_key, to=transition_name)
                return
        logger.warning("dummy_transition_not_found", key=issue_key)

    def add_comment(self, issue_key: str, body: str) -> str:
        """Create or overwrite the single step-notification comment for this issue; return its id."""
        comments_dir = self._base / "comments"
        comments_dir.mkdir(parents=True, exist_ok=True)
        safe_key = issue_key.replace("-", "_")
        comment_id = f"dummy-{safe_key}"
        log_path = comments_dir / f"{safe_key}.txt"
        log_path.write_text(body, encoding="utf-8")
        logger.info("dummy_comment_added", issue_key=issue_key)
        return comment_id

    def update_comment(self, issue_key: str, comment_id: str, body: str) -> None:
        """Overwrite the step-notification comment body (same single comment per issue)."""
        safe_key = issue_key.replace("-", "_")
        expected_id = f"dummy-{safe_key}"
        if comment_id != expected_id:
            logger.warning("dummy_update_comment_id_mismatch", issue_key=issue_key)
            return
        comments_dir = self._base / "comments"
        log_path = comments_dir / f"{safe_key}.txt"
        if log_path.exists():
            log_path.write_text(body, encoding="utf-8")
            logger.info("dummy_comment_updated", issue_key=issue_key)

    def set_story_branch_field(self, story_key: str, branch: str) -> None:
        """No-op in dummy; real implementation updates customfield_10145."""
        logger.info("dummy_set_story_branch_field", story_key=story_key, branch=branch)
