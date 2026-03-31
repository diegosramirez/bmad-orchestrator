from __future__ import annotations

from bmad_orchestrator.utils.jira_adf import (
    adf_to_markdown,
    description_for_jira_api,
    description_from_jira_api,
    markdown_to_adf,
)


def test_markdown_to_adf_empty() -> None:
    doc = markdown_to_adf("")
    assert doc == {"type": "doc", "version": 1, "content": []}


def test_markdown_to_adf_heading_and_paragraph() -> None:
    doc = markdown_to_adf("# Discovery\n\nHello world.")
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    c = doc["content"]
    assert c[0]["type"] == "heading"
    assert c[0]["attrs"]["level"] == 1
    assert c[0]["content"][0]["text"] == "Discovery"
    assert c[1]["type"] == "paragraph"


def test_markdown_to_adf_bold_double_star() -> None:
    doc = markdown_to_adf("Some **bold** text.")
    para = doc["content"][0]
    assert para["type"] == "paragraph"
    parts = para["content"]
    assert parts[0]["text"] == "Some "
    assert parts[1]["marks"][0]["type"] == "strong"
    assert parts[1]["text"] == "bold"


def test_markdown_to_adf_fenced_mermaid() -> None:
    md = "```mermaid\nflowchart LR\n  A-->B\n```"
    doc = markdown_to_adf(md)
    blk = doc["content"][0]
    assert blk["type"] == "codeBlock"
    assert blk["attrs"].get("language") == "mermaid"
    assert "flowchart" in blk["content"][0]["text"]


def test_markdown_to_adf_bullet_list() -> None:
    doc = markdown_to_adf("- one\n- two")
    assert doc["content"][0]["type"] == "bulletList"
    items = doc["content"][0]["content"]
    assert len(items) == 2


def test_adf_round_trip_partial() -> None:
    md = "# Title\n\nPara *x* and **y**."
    back = adf_to_markdown(markdown_to_adf(md))
    assert "Title" in back
    assert "Para" in back


def test_description_for_api_and_from_api() -> None:
    d = description_for_jira_api("# A\n\nb")
    assert d["type"] == "doc"
    assert description_from_jira_api(d) == adf_to_markdown(d)
    assert description_from_jira_api("plain") == "plain"


def test_description_from_jira_api_none() -> None:
    assert description_from_jira_api(None) == ""
