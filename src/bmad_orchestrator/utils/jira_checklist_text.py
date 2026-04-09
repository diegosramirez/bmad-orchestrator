"""Build Checklists for Jira | Free \"Checklist Text\" markdown from task lists."""

from __future__ import annotations

import re
from typing import Any

# Lines from ``tasks_to_checklist_markdown``: * [ ] or * [x] **summary** — optional tail
_CHECKLIST_LINE = re.compile(
    r"^(\*)\s+\[([ xX])\]\s+(\*\*)(.+?)(\*\*)(.*)$",
)


def _normalize_summary_key(summary: str) -> str:
    """Normalize summary text for fuzzy matching (same idea as story dedupe keys)."""
    s = (summary or "").strip().lower()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def mark_checklist_items_done(markdown: str, completed_summaries: list[str]) -> str:
    """Turn ``[ ]`` into ``[x]`` where the bold summary matches *completed_summaries*.

    Unknown names are ignored. Lines already ``[x]`` are left as-is.
    """
    if not markdown.strip() or not completed_summaries:
        return markdown
    done_keys = {_normalize_summary_key(s) for s in completed_summaries if s.strip()}
    done_keys.discard("")
    if not done_keys:
        return markdown

    out_lines: list[str] = []
    for line in markdown.splitlines():
        m = _CHECKLIST_LINE.match(line.rstrip())
        if not m:
            out_lines.append(line)
            continue
        star, box, o1, summary, o2, tail = m.groups()
        key = _normalize_summary_key(summary)
        if box.strip().lower() == "x" or key not in done_keys:
            out_lines.append(line)
            continue
        # Unchecked and in done_keys → mark checked
        new_line = f"{star} [x] {o1}{summary}{o2}{tail}"
        out_lines.append(new_line)
    return "\n".join(out_lines)


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
