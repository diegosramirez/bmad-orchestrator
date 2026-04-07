"""Parse ``/bmad retry`` / ``/bmad refine`` commands from Jira comment text (multiline-safe)."""
from __future__ import annotations

import re

BMAD_COMMENT_USAGE = 'Usage: /bmad retry "guidance" or /bmad refine "guidance"'


def parse_bmad_comment_command(text: str) -> tuple[str | None, str, str | None]:
    """Parse ``/bmad retry|refine`` and optional multiline guidance (no shell quoting).

    Returns ``(subcommand, guidance, error)``. On success ``error`` is ``None`` and
    ``subcommand`` is ``retry`` or ``refine``. ``guidance`` may be empty.
    """
    raw = text.strip()
    m = re.match(r"\A/bmad\s+(retry|refine)\b\s*(.*)\Z", raw, re.DOTALL | re.IGNORECASE)
    if m:
        subcommand = m.group(1).lower()
        rest = m.group(2).strip()
        if len(rest) >= 2:
            first, last = rest[0], rest[-1]
            if (first, last) in (('"', '"'), ("\u201c", "\u201d")):
                rest = rest[1:-1]
        return (subcommand, rest, None)

    if not raw.startswith("/bmad"):
        return (None, "", "not_bmad")

    mw = re.match(r"\A/bmad\s+(\S+)", raw)
    if mw and mw.group(1).lower() not in ("retry", "refine"):
        return (None, "", f"Unknown /bmad subcommand: {mw.group(1)}")

    return (None, "", BMAD_COMMENT_USAGE)
