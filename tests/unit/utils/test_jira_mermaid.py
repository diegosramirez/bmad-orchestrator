from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.jira_mermaid import (
    build_description_adf_with_mermaid,
    markdown_intermediate_without_mermaid_images,
    media_single_adf_node,
    mermaid_pipeline_enabled,
    split_markdown_mermaid_segments,
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
    assert "Mermaid diagram will be attached" in out


def test_media_single_adf_node_shape() -> None:
    node = media_single_adf_node("id-1", 100, 50, "d.png", "")
    assert node["type"] == "mediaSingle"
    assert node["attrs"]["layout"] == "center"
    media = node["content"][0]
    assert media["type"] == "media"
    assert media["attrs"]["id"] == "id-1"
    assert media["attrs"]["width"] == 100
    assert media["attrs"]["height"] == 50


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


def test_build_adf_mermaid_uses_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        github_repo="a/b",
        mermaid_renderer="kroki",
    )

    def fake_render(_settings: Settings, _src: str) -> tuple[bytes | None, str | None]:
        return _PNG_1X1, None

    monkeypatch.setattr(
        "bmad_orchestrator.utils.jira_mermaid.render_mermaid_to_png",
        fake_render,
    )

    att = MagicMock()
    att.id = "att-42"

    def add_attachment(_ik: str, _fp: BytesIO, _fn: str) -> MagicMock:
        return att

    doc = build_description_adf_with_mermaid(
        "Hi\n\n```mermaid\nflowchart LR\n  A-->B\n```",
        s,
        "ISS-1",
        add_attachment,
    )
    blocks = doc["content"]
    assert any(b.get("type") == "paragraph" for b in blocks)
    media_blocks = [b for b in blocks if b.get("type") == "mediaSingle"]
    assert len(media_blocks) == 1
    assert media_blocks[0]["content"][0]["attrs"]["id"] == "att-42"


def test_build_description_fallback_on_render_failure(monkeypatch: pytest.MonkeyPatch) -> None:
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

    doc = build_description_adf_with_mermaid(
        "```mermaid\nbad\n```",
        s,
        "ISS-1",
        lambda *a: MagicMock(),
    )
    assert doc["content"][0]["type"] == "codeBlock"
    assert doc["content"][0]["attrs"].get("language") == "mermaid"
