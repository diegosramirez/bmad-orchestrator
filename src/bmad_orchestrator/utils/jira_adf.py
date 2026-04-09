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


def _split_table_row(line: str) -> list[str]:
    """Split a pipe table row into cell strings (trimmed)."""
    raw = line.strip()
    if not raw or "|" not in raw:
        return []
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [c.strip() for c in raw.split("|")]


def _is_gfm_separator_row(line: str) -> bool:
    """True if ``line`` is a GFM table alignment row (``| --- | --- |``)."""
    cells = _split_table_row(line)
    if len(cells) < 2:
        return False
    for c in cells:
        if not re.match(r"^:?-{3,}:?$", c.strip()):
            return False
    return True


def _adf_table_cell(cell_type: str, cell_text: str) -> dict[str, Any]:
    return {
        "type": cell_type,
        "attrs": {},
        "content": [_paragraph_from_text(cell_text)],
    }


def _adf_gfm_table(header_cells: list[str], body_rows: list[list[str]]) -> dict[str, Any]:
    """Build ADF ``table`` from parsed GFM header + body (Jira Cloud table node schema)."""
    header_row: list[dict[str, Any]] = [
        _adf_table_cell("tableHeader", h) for h in header_cells
    ]
    rows: list[dict[str, Any]] = [{"type": "tableRow", "content": header_row}]
    for body in body_rows:
        cells = [_adf_table_cell("tableCell", c) for c in body]
        rows.append({"type": "tableRow", "content": cells})
    return {
        "type": "table",
        "attrs": {
            "isNumberColumnEnabled": False,
            "layout": "align-start",
            "width": 760,
            "displayMode": "default",
        },
        "content": rows,
    }


def _try_parse_gfm_table(lines: list[str], i: int) -> tuple[dict[str, Any] | None, int]:
    """
    If ``lines[i:]`` begins a GFM pipe table (header + separator + optional body), return
    ``(table_node, next_index)``. Otherwise ``(None, i)``.
    """
    if i + 1 >= len(lines):
        return None, i
    row0 = lines[i].strip()
    row1 = lines[i + 1].strip()
    if "|" not in row0 or not row1:
        return None, i
    if not _is_gfm_separator_row(row1):
        return None, i
    header_cells = _split_table_row(row0)
    sep_cells = _split_table_row(row1)
    if len(header_cells) < 2 or len(header_cells) != len(sep_cells):
        return None, i
    ncols = len(header_cells)
    body_rows: list[list[str]] = []
    j = i + 2
    while j < len(lines):
        ln = lines[j].strip()
        if not ln:
            break
        if "|" not in ln:
            break
        cells = _split_table_row(ln)
        if len(cells) == 1 and ncols > 1:
            break
        if len(cells) < ncols:
            while len(cells) < ncols:
                cells.append("")
        elif len(cells) > ncols:
            cells = cells[:ncols]
        body_rows.append(cells)
        j += 1
    return _adf_gfm_table(header_cells, body_rows), j


def _table_row_to_markdown(row: dict[str, Any]) -> str:
    cells: list[str] = []
    for cell in row.get("content") or []:
        if not isinstance(cell, dict):
            continue
        if cell.get("type") not in ("tableCell", "tableHeader"):
            continue
        text = ""
        for inner in cell.get("content") or []:
            if not isinstance(inner, dict):
                continue
            if inner.get("type") == "paragraph":
                text = _inline_from_adf(inner.get("content") or [])
                break
        cells.append(text.replace("\n", " ").strip())
    return "| " + " | ".join(cells) + " |"


def _table_to_markdown(block: dict[str, Any]) -> str:
    lines_out: list[str] = []
    for row in block.get("content") or []:
        if row.get("type") != "tableRow":
            continue
        lines_out.append(_table_row_to_markdown(row))
    if len(lines_out) < 2:
        return "\n".join(lines_out)
    ncols = len(_split_table_row(lines_out[0]))
    sep = "| " + " | ".join(["---"] * ncols) + " |"
    return lines_out[0] + "\n" + sep + "\n" + "\n".join(lines_out[1:])


def markdown_to_adf(markdown: str) -> dict[str, Any]:
    """
    Convert a subset of Markdown to Jira ADF ``{"type": "doc", ...}``.

    Supports: ATX headings, paragraphs, bullet lists, fenced code blocks, ** / * bold,
    GFM pipe tables (header row + ``---`` separator + body rows).
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

        tbl, j = _try_parse_gfm_table(lines, i)
        if tbl is not None:
            content.append(tbl)
            i = j
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
    """Extract plain text from inline ADF nodes (text, line breaks, emoji, etc.)."""
    parts: list[str] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = n.get("type")
        if ntype == "text":
            t = n.get("text") or ""
            marks = n.get("marks") or []
            is_strong = any(m.get("type") == "strong" for m in marks)
            if is_strong:
                parts.append(f"*{t}*")
            else:
                parts.append(t)
        elif ntype == "hardBreak":
            parts.append("\n")
        elif ntype == "emoji":
            attrs = n.get("attrs") or {}
            parts.append(str(attrs.get("text") or attrs.get("shortName") or ""))
        elif ntype == "mention":
            attrs = n.get("attrs") or {}
            parts.append(str(attrs.get("text") or attrs.get("id") or "mention"))
        elif ntype in ("inlineCard", "date"):
            attrs = n.get("attrs") or {}
            if isinstance(attrs.get("url"), str):
                parts.append(attrs["url"])
            elif isinstance(attrs.get("timestamp"), str):
                parts.append(attrs["timestamp"])
    return "".join(parts)


def _adf_collect_plain_text(node: Any) -> str:
    """Deep-recursively collect all ``text`` node payloads (fallback for unknown block types)."""
    chunks: list[str] = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            if n.get("type") == "text" and "text" in n:
                t = n.get("text")
                if isinstance(t, str) and t:
                    chunks.append(t)
            for c in n.get("content") or []:
                walk(c)
            attrs = n.get("attrs")
            if isinstance(attrs, dict):
                for k in ("text", "title", "alt", "label"):
                    v = attrs.get(k)
                    if isinstance(v, str) and v:
                        chunks.append(v)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(node)
    return " ".join(chunks)


def _bullet_list_to_markdown(block: dict[str, Any], indent: str) -> str:
    lines: list[str] = []
    for li in block.get("content") or []:
        if li.get("type") != "listItem":
            continue
        chunk = _list_item_to_markdown(li, indent)
        if chunk:
            lines.append(chunk)
    return "\n".join(lines)


def _ordered_list_to_markdown(block: dict[str, Any], indent: str) -> str:
    lines: list[str] = []
    idx = 1
    for li in block.get("content") or []:
        if li.get("type") != "listItem":
            continue
        chunk = _list_item_to_markdown_numbered(li, indent, idx)
        idx += 1
        if chunk:
            lines.append(chunk)
    return "\n".join(lines)


def _list_item_to_markdown(li: dict[str, Any], indent: str) -> str:
    """Render one bullet list item (may contain nested lists)."""
    parts: list[str] = []
    for child in li.get("content") or []:
        if not isinstance(child, dict):
            continue
        ct = child.get("type")
        if ct == "paragraph":
            parts.append(f"{indent}- {_inline_from_adf(child.get('content') or [])}")
        elif ct == "bulletList":
            nested = _bullet_list_to_markdown(child, indent + "  ")
            if nested:
                parts.append(nested)
        elif ct == "orderedList":
            nested = _ordered_list_to_markdown(child, indent + "  ")
            if nested:
                parts.append(nested)
        elif ct == "heading":
            level = (child.get("attrs") or {}).get("level") or 1
            hashes = "#" * int(level)
            title = _inline_from_adf(child.get("content") or [])
            parts.append(f"{indent}- {hashes} {title}")
        elif ct == "blockquote":
            inner = _blockquote_to_markdown(child)
            if inner:
                parts.append(f"{indent}- {inner}")
        else:
            md = _block_to_markdown_impl(child, use_plain_fallback=True)
            if md:
                parts.append(f"{indent}- {md}")
    return "\n".join(parts)


def _list_item_to_markdown_numbered(li: dict[str, Any], indent: str, num: int) -> str:
    parts: list[str] = []
    for child in li.get("content") or []:
        if not isinstance(child, dict):
            continue
        ct = child.get("type")
        if ct == "paragraph":
            parts.append(f"{indent}{num}. {_inline_from_adf(child.get('content') or [])}")
        elif ct == "bulletList":
            nested = _bullet_list_to_markdown(child, indent + "  ")
            if nested:
                parts.append(nested)
        elif ct == "orderedList":
            nested = _ordered_list_to_markdown(child, indent + "  ")
            if nested:
                parts.append(nested)
        else:
            md = _block_to_markdown_impl(child, use_plain_fallback=True)
            if md:
                parts.append(f"{indent}{num}. {md}")
    return "\n".join(parts)


def _blockquote_to_markdown(block: dict[str, Any]) -> str:
    lines: list[str] = []
    for inner in block.get("content") or []:
        if isinstance(inner, dict):
            md = _block_to_markdown_impl(inner, use_plain_fallback=True)
            if md:
                lines.append(md)
    return " ".join(lines)


def _block_to_markdown(block: dict[str, Any]) -> str:
    return _block_to_markdown_impl(block, use_plain_fallback=True)


def _block_to_markdown_impl(block: dict[str, Any], *, use_plain_fallback: bool) -> str:
    btype = block.get("type")
    if btype == "paragraph":
        return _inline_from_adf(block.get("content") or [])
    if btype == "heading":
        level = (block.get("attrs") or {}).get("level") or 1
        hashes = "#" * int(level)
        title = _inline_from_adf(block.get("content") or [])
        return f"{hashes} {title}"
    if btype == "bulletList":
        return _bullet_list_to_markdown(block, "")
    if btype == "codeBlock":
        lang = (block.get("attrs") or {}).get("language") or ""
        text = ""
        for c in block.get("content") or []:
            if c.get("type") == "text":
                text += c.get("text") or ""
        fence = "```" + (lang or "")
        return f"{fence}\n{text}\n```"
    if btype == "orderedList":
        return _ordered_list_to_markdown(block, "")
    if btype == "blockquote":
        return _blockquote_to_markdown(block)
    if btype == "table":
        return _table_to_markdown(block)
    if btype == "rule":
        return "---"
    if btype in ("panel", "extension", "expand", "nestedExpand"):
        inner = _adf_collect_plain_text(block)
        return inner if inner else ""
    if btype == "mediaSingle":
        return "[Diagram attached]"
    if btype == "mediaGroup":
        return ""
    if use_plain_fallback:
        return _adf_collect_plain_text(block)
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


def is_adf_document(val: Any) -> bool:
    """True if *val* is an Atlassian Document (ADF) root (``type`` == ``doc``)."""
    if isinstance(val, dict) and val.get("type") == "doc":
        return True
    return getattr(val, "type", None) == "doc"


def paragraph_custom_field_payload_for_api(before: Any, markdown: str) -> Any:
    """Paragraph / rich-text custom fields: ADF when the field already uses ADF; else plain str."""
    if before is not None and not is_adf_document(before) and isinstance(before, str):
        return markdown
    return description_for_jira_api(markdown)


def _jira_adf_payload_to_dict(obj: Any) -> Any:
    """Turn python-jira ``PropertyHolder`` trees (nested ADF) into plain ``dict``/list for parsing.

    The jira library parses JSON ``fields.description`` into ``PropertyHolder`` objects.
    ``str()`` on those yields a useless ~56-char repr; we need the real structure.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _jira_adf_payload_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jira_adf_payload_to_dict(x) for x in obj]
    if hasattr(obj, "__dict__"):
        d = vars(obj)
        if d and not isinstance(obj, type):
            return {
                k: _jira_adf_payload_to_dict(v)
                for k, v in d.items()
                if not str(k).startswith("_")
            }
    return obj


def description_from_jira_api(raw: Any) -> str:
    """Normalise API description (string or ADF doc) to markdown string."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict) and raw.get("type") == "doc":
        return adf_to_markdown(raw)
    # python-jira wraps ADF JSON in PropertyHolder (not a dict); convert then parse.
    if getattr(raw, "type", None) == "doc" and hasattr(raw, "content"):
        as_dict = _jira_adf_payload_to_dict(raw)
        if isinstance(as_dict, dict) and as_dict.get("type") == "doc":
            return adf_to_markdown(as_dict)
    return str(raw)
