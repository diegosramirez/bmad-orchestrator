from __future__ import annotations

import re

_FIGMA_URL_RE = re.compile(
    r"https?://(?:www\.)?figma\.com/(?:file|design|proto|board)/"
    r"[A-Za-z0-9]+(?:/[^\s)>\]]*)?",
    re.IGNORECASE,
)


def extract_figma_url(text: str | None) -> str | None:
    """Return the first Figma URL found in text, or None.

    Accepts free-form prose, markdown, or Jira ADF-serialized content with URLs
    wrapped in link text, brackets, or parentheses.
    """
    if not text:
        return None
    match = _FIGMA_URL_RE.search(text)
    return match.group(0) if match else None
