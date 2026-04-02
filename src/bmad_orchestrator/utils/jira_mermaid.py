"""Mermaid fences: render to PNG, attach to issue. No inline ADF media in description."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from typing import Any, Literal

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.mermaid_render import (
    has_mermaid_fences,
    render_mermaid_to_png,
)

logger = get_logger(__name__)

_MermaidSeg = tuple[Literal["text", "mermaid"], str]


def split_markdown_mermaid_segments(markdown: str) -> list[_MermaidSeg]:
    """Split markdown into alternating text and mermaid fence bodies (no fences)."""
    text = (markdown or "").replace("\r\n", "\n")
    lines = text.split("\n")
    segments: list[_MermaidSeg] = []
    i = 0
    n = len(lines)
    buf: list[str] = []

    def flush_text() -> None:
        if buf:
            segments.append(("text", "\n".join(buf)))
            buf.clear()

    while i < n:
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            if lang.lower() == "mermaid":
                flush_text()
                i += 1
                code_lines: list[str] = []
                while i < n and lines[i].strip() != "```":
                    code_lines.append(lines[i])
                    i += 1
                if i < n and lines[i].strip() == "```":
                    i += 1
                segments.append(("mermaid", "\n".join(code_lines)))
                continue
        buf.append(lines[i])
        i += 1
    flush_text()
    if not segments:
        segments.append(("text", text))
    return segments


def markdown_intermediate_without_mermaid_images(markdown: str) -> str:
    """Replace ```mermaid fences with a short note; diagrams are attached separately."""
    segments = split_markdown_mermaid_segments(markdown)
    parts: list[str] = []
    for kind, seg in segments:
        if kind == "text":
            parts.append(seg)
        else:
            parts.append(
                "\n\n*[Mermaid diagram — review it in the Attachments section.]*\n\n",
            )
    return "".join(parts)


def upload_mermaid_png_attachments(
    markdown: str,
    settings: Settings,
    issue_key: str,
    add_attachment: Callable[[str, BytesIO, str], Any],
) -> None:
    """
    Render each ```mermaid fence to PNG and attach to the issue.

    Jira Cloud does not reliably expose a Media Services file id via the classic attachment
    REST API for ADF ``media`` nodes. We only upload files; the description should use
    ``markdown_intermediate_without_mermaid_images`` so the body references attachments.
    """
    segments = split_markdown_mermaid_segments(markdown)
    diagram_idx = 0
    for kind, seg in segments:
        if kind != "mermaid":
            continue
        png, err = render_mermaid_to_png(settings, seg)
        if err or not png:
            logger.info(
                "mermaid_render_skip_attachment",
                issue_key=issue_key,
                diagram_index=diagram_idx,
                error=err,
            )
            diagram_idx += 1
            continue
        fname = f"mermaid-{diagram_idx}.png"
        diagram_idx += 1
        try:
            add_attachment(issue_key, BytesIO(png), fname)
        except Exception as exc:
            logger.warning(
                "mermaid_attachment_failed",
                issue_key=issue_key,
                filename=fname,
                error=str(exc),
            )


def mermaid_pipeline_enabled(settings: Settings, markdown: str) -> bool:
    """True when renderer is on and markdown contains ```mermaid fences."""
    r = (settings.mermaid_renderer or "off").lower()
    return r in ("kroki", "mmdc") and has_mermaid_fences(markdown)
