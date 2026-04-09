from __future__ import annotations

from bmad_orchestrator.nodes.create_story_tasks import TaskItem
from bmad_orchestrator.utils.jira_checklist_text import tasks_to_checklist_markdown


def test_tasks_to_checklist_markdown_formats_items() -> None:
    md = tasks_to_checklist_markdown([
        TaskItem(summary="First", description="Do one thing"),
        TaskItem(summary="Second", description=""),
    ])
    assert "## Implementation checklist" not in md
    assert "* [ ] **First** — Do one thing" in md
    assert "* [ ] **Second**" in md


def test_tasks_to_checklist_markdown_skips_empty_summary() -> None:
    md = tasks_to_checklist_markdown([
        TaskItem(summary="", description="ignored"),
        TaskItem(summary="Keep", description="x"),
    ])
    assert "ignored" not in md
    assert "Keep" in md
