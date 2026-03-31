"""Atlassian Document Format (ADF) for Jira Cloud REST API v3 issue descriptions."""

from __future__ import annotations

import re
from typing import Any


def _merge_adjacent_text_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in nodes:
        if not out:
            out.append(n)
            continue
        if n.get("type") == "text" and out[-1].get("type") == "text":
            om = out[-1].get("marks")
            nm = n.get("marks")
            if om == nm:
                out[-1]["text"] = (out[-1].get("text") or "") + (n.get("text") or "")
                continue
        out.append(n)
    return out


def parse_inline_to_adf(text: str) -> list[dict[str, Any]]:
    """Convert inline **bold** and *bold* to ADF text nodes with strong marks."""
    if not text:
        return []
    nodes: list[dict[str, Any]] = []
    pos = 0
    for m in re.finditer(r"\*\*(.+?)\*\*", text, flags=re.DOTALL):
        if m.start() > pos:
            nodes.extend(_single_star_segments(text[pos : m.start()]))
        nodes.append(
            {"type": "text", "text": m.group(1), "marks": [{"type": "strong"}]},
        )
        pos = m.end()
    if pos < len(text):
        nodes.extend(_single_star_segments(text[pos:]))
    return _merge_adjacent_text_nodes(nodes)


def _single_star_segments(fragment: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pos = 0
    for m in re.finditer(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", fragment):
        if m.start() > pos:
            t = fragment[pos : m.start()]
            if t:
                out.append({"type": "text", "text": t})
        out.append(
            {"type": "text", "text": m.group(1), "marks": [{"type": "strong"}]},
        )
        pos = m.end()
    if pos < len(fragment):
        out.append({"type": "text", "text": fragment[pos:]})
    return out


def _paragraph_from_text(text: str) -> dict[str, Any]:
    content = parse_inline_to_adf(text.strip())
    if not content:
        return {"type": "paragraph", "content": []}
    return {"type": "paragraph", "content": content}


def _heading_node(level: int, title: str) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": min(max(level, 1), 6)},
        "content": parse_inline_to_adf(title),
    }


def _bullet_list(items: list[str]) -> dict[str, Any]:
    list_items: list[dict[str, Any]] = []
    for item in items:
        list_items.append(
            {
                "type": "listItem",
                "content": [_paragraph_from_text(item)],
            }
        )
    return {"type": "bulletList", "content": list_items}


def _code_block(code: str, language: str | None) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if language:
        attrs["language"] = language
    return {
        "type": "codeBlock",
        "attrs": attrs,
        "content": [{"type": "text", "text": code}],
    }


def markdown_to_adf(markdown: str) -> dict[str, Any]:
    """
    Convert a subset of Markdown to Jira ADF ``{"type": "doc", ...}``.

    Supports: ATX headings, paragraphs, bullet lists, fenced code blocks, ** / * bold.
    """
    text = (markdown or "").replace("\r\n", "\n")
    lines = text.split("\n")
    content: list[dict[str, Any]] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip() or ""
            code_lines: list[str] = []
            i += 1
            while i < n and lines[i].strip() != "```":
                code_lines.append(lines[i])
                i += 1
            if i < n and lines[i].strip() == "```":
                i += 1
            content.append(_code_block("\n".join(code_lines), lang or None))
            continue

        hm = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if hm:
            level = len(hm.group(1))
            title = hm.group(2).strip()
            content.append(_heading_node(level, title))
            i += 1
            continue

        if re.match(r"^[-*]\s+", stripped):
            items: list[str] = []
            while i < n:
                s2 = lines[i].strip()
                if re.match(r"^[-*]\s+", s2):
                    items.append(re.sub(r"^[-*]\s+", "", s2))
                    i += 1
                elif not s2:
                    i += 1
                    break
                else:
                    break
            if items:
                content.append(_bullet_list(items))
            continue

        para_lines: list[str] = []
        while i < n:
            s2 = lines[i].strip()
            if not s2:
                break
            if (
                s2.startswith("```")
                or re.match(r"^#{1,6}\s+", s2)
                or re.match(r"^[-*]\s+", s2)
            ):
                break
            para_lines.append(s2)
            i += 1
        body = "\n".join(para_lines)
        if body.strip():
            for chunk in body.split("\n"):
                if chunk.strip():
                    content.append(_paragraph_from_text(chunk))

    if not content:
        return {"type": "doc", "version": 1, "content": []}
    return {"type": "doc", "version": 1, "content": content}


def _inline_from_adf(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for n in nodes:
        if n.get("type") != "text":
            continue
        t = n.get("text") or ""
        marks = n.get("marks") or []
        is_strong = any(m.get("type") == "strong" for m in marks)
        if is_strong:
            parts.append(f"*{t}*")
        else:
            parts.append(t)
    return "".join(parts)


def _block_to_markdown(block: dict[str, Any]) -> str:
    btype = block.get("type")
    if btype == "paragraph":
        return _inline_from_adf(block.get("content") or [])
    if btype == "heading":
        level = (block.get("attrs") or {}).get("level") or 1
        hashes = "#" * int(level)
        title = _inline_from_adf(block.get("content") or [])
        return f"{hashes} {title}"
    if btype == "bulletList":
        lines = []
        for li in block.get("content") or []:
            if li.get("type") != "listItem":
                continue
            for inner in li.get("content") or []:
                if inner.get("type") == "paragraph":
                    lines.append("- " + _inline_from_adf(inner.get("content") or []))
        return "\n".join(lines)
    if btype == "codeBlock":
        lang = (block.get("attrs") or {}).get("language") or ""
        text = ""
        for c in block.get("content") or []:
            if c.get("type") == "text":
                text += c.get("text") or ""
        fence = "```" + (lang or "")
        return f"{fence}\n{text}\n```"
    if btype == "orderedList":
        lines = []
        idx = 1
        for li in block.get("content") or []:
            if li.get("type") != "listItem":
                continue
            for inner in li.get("content") or []:
                if inner.get("type") == "paragraph":
                    lines.append(f"{idx}. {_inline_from_adf(inner.get('content') or [])}")
                    idx += 1
        return "\n".join(lines)
    return ""


def adf_to_markdown(doc: Any) -> str:
    """Best-effort ADF document to markdown for orchestrator / Claude context."""
    if doc is None:
        return ""
    if isinstance(doc, str):
        return doc
    if not isinstance(doc, dict):
        return str(doc)
    if doc.get("type") != "doc":
        return str(doc)
    parts: list[str] = []
    for block in doc.get("content") or []:
        if isinstance(block, dict):
            md = _block_to_markdown(block)
            if md:
                parts.append(md)
    return "\n\n".join(parts)


def description_for_jira_api(markdown: str) -> dict[str, Any]:
    """Jira Cloud issue field payload: ADF document dict."""
    return markdown_to_adf(markdown)


def description_from_jira_api(raw: Any) -> str:
    """Normalise API description (string or ADF doc) to markdown string."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict) and raw.get("type") == "doc":
        return adf_to_markdown(raw)
    return str(raw)
