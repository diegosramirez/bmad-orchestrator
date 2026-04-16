from __future__ import annotations

from bmad_orchestrator.nodes.create_story_tasks import TaskItem
from bmad_orchestrator.utils.jira_checklist_text import (
    CHECKLIST_LINE_RENDER_MAX,
    CHECKLIST_TASK_DESCRIPTION_MAX_LEN,
    mark_checklist_items_done,
    tasks_to_checklist_markdown,
    truncate_checklist_field,
)


def test_truncate_checklist_field_adds_ellipsis() -> None:
    long = "x" * 50
    out = truncate_checklist_field(long, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_tasks_to_checklist_markdown_truncates_long_description() -> None:
    long_desc = "word " * 200
    md = tasks_to_checklist_markdown([
        TaskItem(summary="Title", description=long_desc),
    ])
    line = md.split("\n")[0]
    assert len(line) <= CHECKLIST_LINE_RENDER_MAX
    assert len(long_desc) > CHECKLIST_TASK_DESCRIPTION_MAX_LEN


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


def test_mark_checklist_items_done_one_item() -> None:
    md = tasks_to_checklist_markdown([
        TaskItem(summary="Alpha", description="a"),
        TaskItem(summary="Beta", description="b"),
    ])
    out = mark_checklist_items_done(md, ["Alpha"])
    assert "* [x] **Alpha**" in out
    assert "* [ ] **Beta**" in out


def test_mark_checklist_items_done_preserves_already_checked() -> None:
    base = "* [x] **Done**\n* [ ] **Todo**"
    out = mark_checklist_items_done(base, ["Todo"])
    assert "* [x] **Done**" in out
    assert "* [x] **Todo**" in out


def test_mark_checklist_items_done_unknown_summary_ignored() -> None:
    md = "* [ ] **Only** — one"
    out = mark_checklist_items_done(md, ["Nope"])
    assert out == md


def test_mark_checklist_items_done_empty_completed_returns_unchanged() -> None:
    md = "* [ ] **A**"
    assert mark_checklist_items_done(md, []) == md


def test_mark_checklist_jira_open_italic_to_done() -> None:
    md = (
        "- [open] *Create Web Worker* — Implement scheduler\n"
        "- [open] *Build cache* — IndexedDB\n"
    )
    out = mark_checklist_items_done(md, ["Create Web Worker"])
    assert "- [done] *Create Web Worker* — Implement scheduler" in out
    assert "- [open] *Build cache*" in out


def test_mark_checklist_jira_open_bold_to_done() -> None:
    md = "- [open] **Alpha** — desc\n- [done] **Beta**"
    out = mark_checklist_items_done(md, ["Alpha"])
    assert "- [done] **Alpha** — desc" in out
    assert "- [done] **Beta**" in out


def test_mark_checklist_dash_bullet_checkbox() -> None:
    md = "- [ ] **Todo** — tail"
    out = mark_checklist_items_done(md, ["Todo"])
    assert "- [x] **Todo** — tail" in out


def test_mark_checklist_jira_open_case_insensitive_state() -> None:
    md = "- [OPEN] *Task*"
    out = mark_checklist_items_done(md, ["Task"])
    assert "- [done] *Task*" in out
