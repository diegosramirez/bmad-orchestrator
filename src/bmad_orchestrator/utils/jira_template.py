"""Jira template utilities: load standard template and detect if content matches it."""

from __future__ import annotations

import re
from pathlib import Path

# Sections that must be present for content to be considered "template-compliant".
# Match bold headings as in docs/template-jira.md (normaliser may add \u200B prefix).
JIRA_TEMPLATE_SECTIONS = [
    "**Hypothesis**",
    "**Intervention**",
    "**Data to Collect**",
    "**Success Threshold**",
    "**Rationale**",
    "**Designs**",
    "**Mechanics**",
    "**Tracking**",
    "**Acceptance Criteria**",
]

# Mapping from plain section names (or outline-style labels) to section titles.
# We prepend a zero-width space (\u200B) to each title so Jira does not treat
# these lines as part of a numbered/outline list (1., a., i.), while keeping
# the visual appearance of a normal bold heading for users.
_SECTION_HEADING_MAP = {
    "description": "\u200B**Description**",
    "hypothesis": "\u200B**Hypothesis**",
    "intervention": "\u200B**Intervention**",
    "data to collect": "\u200B**Data to Collect**",
    "success threshold": "\u200B**Success Threshold**",
    "rationale": "\u200B**Rationale**",
    "designs": "\u200B**Designs**",
    "mechanics": "\u200B**Mechanics**",
    "tracking": "\u200B**Tracking**",
    "acceptance criteria": "\u200B**Acceptance Criteria**",
    "implementation notes": "\u200B**Implementation Notes**",
}


def _template_path(app_root: Path | None = None) -> Path:
    """Return the path to docs/template-jira.md relative to the orchestrator app root."""
    if app_root is not None:
        return app_root / "docs" / "template-jira.md"
    # From src/bmad_orchestrator/utils/ -> app root is parent.parent.parent
    utils_dir = Path(__file__).resolve().parent
    app_root = utils_dir.parent.parent.parent
    return app_root / "docs" / "template-jira.md"


def load_template(app_root: Path | None = None) -> str:
    """Load docs/template-jira.md and return its content. Returns empty string if missing."""
    path = _template_path(app_root)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def matches_template(content: str) -> bool:
    """Return True if content contains all template sections."""
    if not (content or "").strip():
        return False
    text = content.strip()
    for section in JIRA_TEMPLATE_SECTIONS:
        if section not in text:
            return False
    return True


# Pattern to strip one or more outline prefixes (1., a., i., ii., etc.) from the start of a string.
_STRIP_OUTLINE_RE = re.compile(r"^\s*(?:\d+\.|[a-zA-Z]+\.)\s*", re.IGNORECASE)


def _strip_all_outline_prefixes(text: str) -> str:
    """Remove all leading '1.', 'a.', 'i.', 'ii.', etc. from text until none remain."""
    while True:
        new_text = _STRIP_OUTLINE_RE.sub("", text, count=1).strip()
        if new_text == text:
            break
        text = new_text
    return text


def normalise_jira_headings(content: str) -> str:
    """
    Normalise outline-style Jira descriptions into canonical markdown headings.

    Some personas like to emit numbered/lettered outlines, e.g.:

        1. Description
           a. Hypothesis
              i. Intervention

    Or even "1. a. i. Description" on one line. Jira then renders these as nested
    lists (1. / a. / i.), which is visually noisy. This helper strips all such
    prefixes and rewrites section names into markdown headings.
    """
    if not content:
        return content

    lines = content.splitlines()
    new_lines: list[str] = []

    # Single outline prefix at start of line: "1. X", "a. X", "i. X", "1. a. i. X"
    outline_pattern = re.compile(r"""^\s*(?:\d+\.|[a-zA-Z]+\.)\s*(?P<label>.*)$""")

    for line in lines:
        stripped = line.strip()

        # Pass 1: line starts with outline prefix (1., a., i., etc.)
        match = outline_pattern.match(stripped)
        if match:
            # Label may still contain more prefixes, e.g. "a. i. Hypothesis"
            raw_label = _strip_all_outline_prefixes(match.group("label")).rstrip(":").strip()

            # Case 1: line was just "1." / "a." / "i." or "1. a. i." with no real label → drop it.
            if not raw_label:
                new_lines.append("")
                continue

            # Case 2: label matches a known template section → replace with heading.
            key = raw_label.lower()
            replacement = _SECTION_HEADING_MAP.get(key)
            if replacement:
                new_lines.append(replacement)
                continue

            # Case 3: unknown label → keep only the text (all outline prefixes already stripped).
            new_lines.append(raw_label)
            continue

        # Pass 2: standalone section name on its own line (no #, no outline)
        if stripped:
            key = stripped.rstrip(":").strip().lower()
            replacement = _SECTION_HEADING_MAP.get(key)
            if replacement:
                new_lines.append(replacement)
                continue

        # Fallback: strip any leading outline prefixes from the line (e.g. "1. a. i. Some text")
        stripped_rest = _strip_all_outline_prefixes(stripped)
        if stripped_rest != stripped:
            if stripped_rest:
                key = stripped_rest.rstrip(":").strip().lower()
                replacement = _SECTION_HEADING_MAP.get(key)
                if replacement:
                    new_lines.append(replacement)
                else:
                    new_lines.append(stripped_rest)
            else:
                new_lines.append("")
            continue
        new_lines.append(line)

    return "\n".join(new_lines)
