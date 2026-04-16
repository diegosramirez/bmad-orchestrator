"""Build Checklists for Jira | Free \"Checklist Text\" markdown from task lists."""

from __future__ import annotations

import re
from typing import Any

# One markdown line per item (required for mark-done regex). Keep each row readable as ~2 lines
# in Jira: short bold title + brief detail.
CHECKLIST_TASK_SUMMARY_MAX_LEN = 80
CHECKLIST_TASK_DESCRIPTION_MAX_LEN = 220
# Hard cap on the full rendered line (markdown + em dash + text).
CHECKLIST_LINE_RENDER_MAX = 310


def truncate_checklist_field(text: str, max_len: int) -> str:
    """Trim a single field; add ellipsis when truncating."""
    s = (text or "").strip()
    if len(s) <= max_len:
        return s
    if max_len < 2:
        return s[:max_len]
    return f"{s[: max_len - 1].rstrip()}…"


# BMAD / markdown checkbox: ``-`` or ``*`` bullet, ``[ ]`` / ``[x]``, ``**summary**``
_CHECKLIST_LINE_CHECKBOX = re.compile(
    r"^([-*])\s+\[([ xX])\]\s+(\*\*)(.+?)(\*\*)(.*)$",
)

# Jira \"Checklist Text\" plugin style: ``[open]`` / ``[done]`` with ``**summary**``
_CHECKLIST_LINE_JIRA_OPEN_BOLD = re.compile(
    r"^([-*])\s+\[(open|done)\]\s+(\*\*)(.+?)(\*\*)(.*)$",
    re.IGNORECASE,
)

# Same plugin with italic single-asterisk title: ``- [open] *summary* — tail``
_CHECKLIST_LINE_JIRA_OPEN_ITALIC = re.compile(
    r"^([-*])\s+\[(open|done)\]\s+\*(.+?)\*(.*)$",
    re.IGNORECASE,
)


def _normalize_summary_key(summary: str) -> str:
    """Normalize summary text for fuzzy matching (same idea as story dedupe keys)."""
    s = (summary or "").strip().lower()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _mark_checklist_line(line: str, done_keys: set[str]) -> str | None:
    """Return the updated line if it is a checklist row to mark done; else None."""
    s = line.rstrip()

    m = _CHECKLIST_LINE_JIRA_OPEN_BOLD.match(s)
    if m:
        bullet, state, o1, summary, o2, tail = m.groups()
        key = _normalize_summary_key(summary)
        if state.lower() == "done" or key not in done_keys:
            return None
        return f"{bullet} [done] {o1}{summary}{o2}{tail}"

    m = _CHECKLIST_LINE_JIRA_OPEN_ITALIC.match(s)
    if m:
        bullet, state, summary, tail = m.groups()
        key = _normalize_summary_key(summary)
        if state.lower() == "done" or key not in done_keys:
            return None
        return f"{bullet} [done] *{summary}*{tail}"

    m = _CHECKLIST_LINE_CHECKBOX.match(s)
    if m:
        bullet, box, o1, summary, o2, tail = m.groups()
        key = _normalize_summary_key(summary)
        if box.strip().lower() == "x" or key not in done_keys:
            return None
        return f"{bullet} [x] {o1}{summary}{o2}{tail}"

    return None


def mark_checklist_items_done(markdown: str, completed_summaries: list[str]) -> str:
    """Mark matching checklist rows as done.

    Supports:

    - BMAD output: ``* [ ] **summary**`` → ``* [x] **summary**`` (``-`` bullet allowed).
    - Jira Checklist Text: ``- [open] *summary*`` or ``- [open] **summary**`` → ``[done]``,
      preserving italic/bold wrappers.

    Unknown summaries are ignored. Already completed lines are left as-is.
    """
    if not markdown.strip() or not completed_summaries:
        return markdown
    done_keys = {_normalize_summary_key(s) for s in completed_summaries if s.strip()}
    done_keys.discard("")
    if not done_keys:
        return markdown

    out_lines: list[str] = []
    for line in markdown.splitlines():
        new_line = _mark_checklist_line(line, done_keys)
        out_lines.append(new_line if new_line is not None else line)
    return "\n".join(out_lines)


def tasks_to_checklist_markdown(tasks: list[Any]) -> str:
    """Turn structured tasks (summary + description) into markdown checklist lines.

    Each item becomes ``* [ ] **summary** — description`` (description collapsed to one line).

    No heading is prepended: Jira Checklist Text treats ``##`` lines as extra checklist rows
    (e.g. ``h2. ...``), so we emit only task lines.

    Summaries and descriptions should already be length-limited (``TaskItem`` validators);
    this function still truncates so Jira rows stay scannable.
    """
    lines: list[str] = []
    for t in tasks:
        summary = truncate_checklist_field(
            str(getattr(t, "summary", "") or ""),
            CHECKLIST_TASK_SUMMARY_MAX_LEN,
        )
        desc_raw = str(getattr(t, "description", "") or "").strip()
        desc_one_line = truncate_checklist_field(
            " ".join(desc_raw.split()),
            CHECKLIST_TASK_DESCRIPTION_MAX_LEN,
        )
        if not summary:
            continue
        if desc_one_line:
            line = f"* [ ] **{summary}** — {desc_one_line}"
        else:
            line = f"* [ ] **{summary}**"
        if len(line) > CHECKLIST_LINE_RENDER_MAX:
            line = truncate_checklist_field(line, CHECKLIST_LINE_RENDER_MAX)
        lines.append(line)
    return "\n".join(lines)
