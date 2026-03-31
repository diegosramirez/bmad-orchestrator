"""Split Markdown with Mermaid fences; build ADF with mediaSingle + attachments."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from typing import Any, Literal

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.jira_adf import _code_block, markdown_to_adf
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.mermaid_render import (
    has_mermaid_fences,
    png_dimensions,
    render_mermaid_to_png,
)

logger = get_logger(__name__)

_MermaidSeg = tuple[Literal["text", "mermaid"], str]

_MAX_MEDIA_DIM = 4096


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
    """Placeholder text for phase-1 create_issue when phase-2 will attach diagrams."""
    segments = split_markdown_mermaid_segments(markdown)
    parts: list[str] = []
    for kind, seg in segments:
        if kind == "text":
            parts.append(seg)
        else:
            parts.append(
                "\n\n*[Mermaid diagram will be attached after issue creation.]*\n\n",
            )
    return "".join(parts)


def _clamp_dim(w: int, h: int) -> tuple[int, int]:
    w = max(1, min(w, _MAX_MEDIA_DIM))
    h = max(1, min(h, _MAX_MEDIA_DIM))
    return w, h


def media_single_adf_node(
    attachment_id: str,
    width: int,
    height: int,
    alt: str,
    collection: str,
) -> dict[str, Any]:
    """ADF mediaSingle block for one inline image from a Jira attachment."""
    w, h = _clamp_dim(width, height)
    return {
        "type": "mediaSingle",
        "attrs": {"layout": "center"},
        "content": [
            {
                "type": "media",
                "attrs": {
                    "id": str(attachment_id),
                    "type": "file",
                    "collection": collection,
                    "alt": alt,
                    "width": w,
                    "height": h,
                },
            }
        ],
    }


def build_description_adf_with_mermaid(
    markdown: str,
    settings: Settings,
    issue_key: str,
    add_attachment: Callable[[str, BytesIO, str], Any],
) -> dict[str, Any]:
    """
    Build full ADF doc: text segments via markdown_to_adf; each mermaid fence rendered
    and attached, then mediaSingle; on render failure, fallback to codeBlock mermaid.
    """
    segments = split_markdown_mermaid_segments(markdown)
    content: list[dict[str, Any]] = []
    diagram_idx = 0
    for kind, seg in segments:
        if kind == "text":
            doc = markdown_to_adf(seg)
            content.extend(doc.get("content") or [])
            continue
        png, err = render_mermaid_to_png(settings, seg)
        if err or not png:
            logger.info(
                "mermaid_render_fallback_code_block",
                issue_key=issue_key,
                error=err,
            )
            content.append(_code_block(seg, "mermaid"))
            continue
        w, h = png_dimensions(png)
        fname = f"mermaid-{diagram_idx}.png"
        diagram_idx += 1
        try:
            att = add_attachment(issue_key, BytesIO(png), fname)
            aid = str(att.id) if hasattr(att, "id") else str(att)
        except Exception as exc:
            logger.warning("mermaid_attachment_failed", issue_key=issue_key, error=str(exc))
            content.append(_code_block(seg, "mermaid"))
            continue
        content.append(
            media_single_adf_node(
                aid,
                w,
                h,
                fname,
                settings.jira_media_collection,
            ),
        )
    if not content:
        return {"type": "doc", "version": 1, "content": []}
    return {"type": "doc", "version": 1, "content": content}


def mermaid_pipeline_enabled(settings: Settings, markdown: str) -> bool:
    """True when renderer is on and markdown contains ```mermaid fences."""
    r = (settings.mermaid_renderer or "off").lower()
    return r in ("kroki", "mmdc") and has_mermaid_fences(markdown)
