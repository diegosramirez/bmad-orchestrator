"""Build Checklists for Jira | Free \"Checklist Text\" markdown from task lists."""

from __future__ import annotations

from typing import Any


def tasks_to_checklist_markdown(tasks: list[Any]) -> str:
    """Turn structured tasks (summary + description) into markdown checklist lines.

    Each item becomes ``* [ ] **summary** — description`` (description collapsed to one line).

    No heading is prepended: Jira Checklist Text treats ``##`` lines as extra checklist rows
    (e.g. ``h2. ...``), so we emit only task lines.
    """
    lines: list[str] = []
    for t in tasks:
        summary = str(getattr(t, "summary", "") or "").strip()
        desc = str(getattr(t, "description", "") or "").strip()
        desc_one_line = " ".join(desc.split())
        if not summary:
            continue
        if desc_one_line:
            lines.append(f"* [ ] **{summary}** — {desc_one_line}")
        else:
            lines.append(f"* [ ] **{summary}**")
    return "\n".join(lines)
