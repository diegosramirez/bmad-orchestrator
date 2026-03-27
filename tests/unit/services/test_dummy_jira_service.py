from __future__ import annotations

from pathlib import Path

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.dummy_jira_service import DummyJiraService


@pytest.fixture
def svc(tmp_path: Path) -> DummyJiraService:
    settings = Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        dummy_jira=True,
        dummy_github=True,
        dummy_data_dir=str(tmp_path),
        dry_run=False,
    )
    return DummyJiraService(settings, base_dir=tmp_path / "jira")


class TestCreateEpic:
    def test_writes_markdown_file(self, svc: DummyJiraService) -> None:
        result = svc.create_epic("Auth Epic", "Implement authentication", "growth")
        assert result["key"].startswith("DUMMY-")
        assert result["summary"] == "Auth Epic"
        assert result["issue_type"] == "Epic"
        assert "growth" in result["labels"]

        # File should exist on disk
        path = svc._base / "epics" / f"EPIC_{result['key']}.md"
        assert path.exists()
        assert "Auth Epic" in path.read_text()

    def test_auto_increments_key(self, svc: DummyJiraService) -> None:
        r1 = svc.create_epic("Epic 1", "desc", "growth")
        r2 = svc.create_epic("Epic 2", "desc", "growth")
        assert r1["key"] == "DUMMY-1"
        assert r2["key"] == "DUMMY-2"


class TestFindEpicByTeam:
    def test_returns_created_epics(self, svc: DummyJiraService) -> None:
        svc.create_epic("Epic A", "desc", "growth")
        svc.create_epic("Epic B", "desc", "growth")
        epics = svc.find_epic_by_team("growth")
        assert len(epics) == 2

    def test_excludes_done_epics(self, svc: DummyJiraService) -> None:
        result = svc.create_epic("Done Epic", "desc", "growth")
        svc.transition_issue(result["key"], "done")
        epics = svc.find_epic_by_team("growth")
        assert len(epics) == 0

    def test_empty_when_no_epics(self, svc: DummyJiraService) -> None:
        assert svc.find_epic_by_team("growth") == []

    def test_excludes_epics_from_other_teams(self, svc: DummyJiraService) -> None:
        svc.create_epic("Growth Epic", "desc", "growth")
        svc.create_epic("Platform Epic", "desc", "platform")
        assert len(svc.find_epic_by_team("growth")) == 1
        assert len(svc.find_epic_by_team("platform")) == 1
        assert svc.find_epic_by_team("other") == []


class TestGetEpic:
    def test_returns_epic_dict(self, svc: DummyJiraService) -> None:
        created = svc.create_epic("My Epic", "desc", "growth")
        fetched = svc.get_epic(created["key"])
        assert fetched is not None
        assert fetched["key"] == created["key"]
        assert fetched["summary"] == "My Epic"

    def test_returns_none_for_missing(self, svc: DummyJiraService) -> None:
        assert svc.get_epic("DUMMY-999") is None


class TestUpdateEpic:
    def test_modifies_and_persists(self, svc: DummyJiraService) -> None:
        created = svc.create_epic("Original", "original desc", "growth")
        updated = svc.update_epic(created["key"], {"description": "updated desc"})
        assert updated["description"] == "updated desc"

        # Re-read from disk
        fetched = svc.get_epic(created["key"])
        assert fetched is not None
        assert fetched["description"] == "updated desc"

    def test_raises_for_missing_epic(self, svc: DummyJiraService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_epic("DUMMY-999", {"description": "x"})


class TestCreateStory:
    def test_creates_with_acceptance_criteria(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Parent", "desc", "growth")
        story = svc.create_story(
            epic["key"], "Login Story", "Implement login", ["AC1", "AC2"], "growth"
        )
        assert story["key"].startswith("DUMMY-")
        assert story["issue_type"] == "Story"
        assert "AC1" in story["description"]
        assert "AC2" in story["description"]
        assert story["parent_key"] == epic["key"]

    def test_get_story_round_trip(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Parent", "desc", "growth")
        created = svc.create_story(epic["key"], "Story", "desc", ["AC1"], "growth")
        fetched = svc.get_story(created["key"])
        assert fetched is not None
        assert fetched["summary"] == "Story"


class TestCreateTask:
    def test_creates_subtask(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Epic", "desc", "growth")
        story = svc.create_story(epic["key"], "Story", "desc", ["AC"], "growth")
        task = svc.create_task(story["key"], "Task 1", "Do something")
        assert task["issue_type"] == "Sub-task"
        assert task["parent_key"] == story["key"]


class TestUpdateStoryDescription:
    def test_updates_description(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Epic", "desc", "growth")
        story = svc.create_story(epic["key"], "Story", "old desc", ["AC"], "growth")
        svc.update_story_description(story["key"], "new desc")
        fetched = svc.get_story(story["key"])
        assert fetched is not None
        assert fetched["description"] == "new desc"


class TestUpdateStorySummary:
    def test_updates_summary(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Epic", "desc", "growth")
        story = svc.create_story(epic["key"], "Story", "desc", ["AC"], "growth")
        svc.update_story_summary(story["key"], "New story title")
        fetched = svc.get_story(story["key"])
        assert fetched is not None
        assert fetched["summary"] == "New story title"


class TestGetSubtasks:
    def test_returns_children_tasks_for_story(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Epic", "desc", "growth")
        story = svc.create_story(epic["key"], "Story", "desc", ["AC"], "growth")
        t1 = svc.create_task(story["key"], "Task 1", "Do something")
        t2 = svc.create_task(story["key"], "Task 2", "Do another thing")
        # Task for another story must not appear
        other_story = svc.create_story(epic["key"], "Other", "desc", ["AC"], "growth")
        svc.create_task(other_story["key"], "Other Task", "Ignore")

        subtasks = svc.get_subtasks(story["key"])
        assert {t["key"] for t in subtasks} == {t1["key"], t2["key"]}


class TestTransitionIssue:
    def test_updates_status(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Epic", "desc", "growth")
        svc.transition_issue(epic["key"], "in progress")
        fetched = svc.get_epic(epic["key"])
        assert fetched is not None
        assert fetched["status"] == "In Progress"


class TestListStoriesUnderEpic:
    def test_returns_only_stories_for_parent_epic(self, svc: DummyJiraService) -> None:
        e1 = svc.create_epic("Epic one", "d", "growth")
        e2 = svc.create_epic("Epic two", "d", "growth")
        s1 = svc.create_story(e1["key"], "Story A", "body", ["AC"], "growth")
        s2 = svc.create_story(e1["key"], "Story B", "body", ["AC"], "growth")
        _ = svc.create_story(e2["key"], "Other epic story", "body", ["AC"], "growth")

        under = svc.list_stories_under_epic(e1["key"])
        assert {x["key"] for x in under} == {s1["key"], s2["key"]}

    def test_empty_when_no_stories(self, svc: DummyJiraService) -> None:
        epic = svc.create_epic("Empty", "d", "growth")
        assert svc.list_stories_under_epic(epic["key"]) == []
