from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.jira_adf import description_for_jira_api
from bmad_orchestrator.utils.jira_mermaid import (
    markdown_intermediate_without_mermaid_images,
    mermaid_pipeline_enabled,
    split_markdown_mermaid_segments,
    upload_mermaid_png_attachments,
)

# 1×1 transparent PNG
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
)


def test_split_markdown_mermaid_segments_alternating() -> None:
    md = "Intro\n\n```mermaid\nflowchart LR\n  A-->B\n```\n\nOutro"
    segs = split_markdown_mermaid_segments(md)
    assert len(segs) == 3
    assert segs[0][0] == "text"
    assert segs[0][1].strip() == "Intro"
    assert "flowchart" in segs[1][1]
    assert segs[1][0] == "mermaid"
    assert segs[2][0] == "text"
    assert segs[2][1].strip() == "Outro"


def test_markdown_intermediate_replaces_mermaid() -> None:
    md = "X\n\n```mermaid\na-->b\n```\n"
    out = markdown_intermediate_without_mermaid_images(md)
    assert "a-->b" not in out
    assert "Mermaid diagram — review it in the Attachments section" in out


def test_mermaid_pipeline_enabled_requires_renderer_and_fence() -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        github_repo="a/b",
        mermaid_renderer="off",
    )
    assert mermaid_pipeline_enabled(s, "```mermaid\nx\n```") is False
    s2 = s.model_copy(update={"mermaid_renderer": "kroki"})
    assert s2.mermaid_renderer == "kroki"
    assert mermaid_pipeline_enabled(s2, "```mermaid\nx\n```") is True


def test_upload_mermaid_png_attachments_calls_add_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        github_repo="a/b",
        mermaid_renderer="kroki",
    )

    monkeypatch.setattr(
        "bmad_orchestrator.utils.jira_mermaid.render_mermaid_to_png",
        lambda _settings, _src: (_PNG_1X1, None),
    )

    calls: list[tuple[str, str]] = []

    def add_attachment(ik: str, _fp: BytesIO, fname: str) -> MagicMock:
        calls.append((ik, fname))
        return MagicMock()

    upload_mermaid_png_attachments(
        "Hi\n\n```mermaid\nflowchart LR\n  A-->B\n```",
        s,
        "ISS-1",
        add_attachment,
    )
    assert calls == [("ISS-1", "mermaid-0.png")]


def test_upload_mermaid_png_skips_attachment_on_render_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        github_repo="a/b",
        mermaid_renderer="kroki",
    )
    monkeypatch.setattr(
        "bmad_orchestrator.utils.jira_mermaid.render_mermaid_to_png",
        lambda _s, _src: (None, "fail"),
    )
    calls: list[str] = []

    def add_attachment(_ik: str, _fp: BytesIO, fname: str) -> MagicMock:
        calls.append(fname)
        return MagicMock()

    upload_mermaid_png_attachments("```mermaid\nbad\n```", s, "ISS-1", add_attachment)
    assert calls == []


def test_mermaid_placeholder_adf_has_no_media_single() -> None:
    """Description path uses placeholder text only; no inline ADF media nodes."""
    md = "```mermaid\nflowchart LR\n  A-->B\n```"
    doc = description_for_jira_api(markdown_intermediate_without_mermaid_images(md))
    assert doc["type"] == "doc"
    blocks = doc.get("content") or []
    assert not any(b.get("type") == "mediaSingle" for b in blocks)
    assert "review it in the Attachments section" in str(doc)
