from __future__ import annotations

from jira.resources import dict2resource

from bmad_orchestrator.utils.jira_adf import (
    adf_to_markdown,
    description_for_jira_api,
    description_from_jira_api,
    markdown_to_adf,
    parse_inline_to_adf,
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


def test_parse_inline_to_adf_markdown_link() -> None:
    nodes = parse_inline_to_adf("[bmad/kan/x](https://github.com/o/r/tree/bmad/kan/x)")
    assert len(nodes) == 1
    assert nodes[0]["text"] == "bmad/kan/x"
    marks = nodes[0]["marks"]
    assert any(m.get("type") == "link" for m in marks)
    link = next(m for m in marks if m.get("type") == "link")
    assert link["attrs"]["href"] == "https://github.com/o/r/tree/bmad/kan/x"


def test_markdown_to_adf_branch_pr_style_line() -> None:
    md = "**Branch:** [feat/foo](https://github.com/org/repo/tree/feat/foo)\n**PR:** [PR #99](https://github.com/org/repo/pull/99)"
    doc = markdown_to_adf(md)
    assert len(doc["content"]) == 2
    p0 = doc["content"][0]["content"]

    def _has_link(n: dict) -> bool:
        return "marks" in n and any(m.get("type") == "link" for m in n["marks"])

    link_node = next(n for n in p0 if _has_link(n))
    assert link_node["text"] == "feat/foo"
    p1 = doc["content"][1]["content"]
    pr_link = next(n for n in p1 if _has_link(n))
    assert pr_link["text"] == "PR #99"


def test_adf_to_markdown_preserves_inline_link() -> None:
    """Link + label survive ADF round-trip; bold uses legacy single-* form in export."""
    md = "**Branch:** [main](https://github.com/o/r/tree/main)"
    doc = markdown_to_adf(md)
    out = adf_to_markdown(doc)
    assert "[main](https://github.com/o/r/tree/main)" in out
    assert "Branch" in out


def test_markdown_to_adf_fenced_mermaid() -> None:
    md = "```mermaid\nflowchart LR\n  A-->B\n```"
    doc = markdown_to_adf(md)
    blk = doc["content"][0]
    assert blk["type"] == "codeBlock"
    assert blk["attrs"].get("language") == "mermaid"
    assert "flowchart" in blk["content"][0]["text"]


def test_adf_to_markdown_media_single_placeholder() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "mediaSingle",
                "attrs": {"layout": "center"},
                "content": [
                    {
                        "type": "media",
                        "attrs": {
                            "id": "1",
                            "type": "file",
                            "collection": "",
                            "alt": "x.png",
                            "width": 10,
                            "height": 10,
                        },
                    },
                ],
            },
        ],
    }
    assert adf_to_markdown(doc) == "[Diagram attached]"


def test_markdown_to_adf_bullet_list() -> None:
    doc = markdown_to_adf("- one\n- two")
    assert doc["content"][0]["type"] == "bulletList"
    items = doc["content"][0]["content"]
    assert len(items) == 2


def test_markdown_to_adf_gfm_table() -> None:
    md = (
        "| Col A | Col B |\n"
        "|-------|-------|\n"
        "| one   | two   |\n"
    )
    doc = markdown_to_adf(md)
    assert doc["content"][0]["type"] == "table"
    tbl = doc["content"][0]
    assert tbl["type"] == "table"
    assert tbl["attrs"]["layout"] == "align-start"
    rows = tbl["content"]
    assert len(rows) == 2
    assert rows[0]["type"] == "tableRow"
    hdr = rows[0]["content"]
    assert hdr[0]["type"] == "tableHeader"
    assert hdr[1]["type"] == "tableHeader"
    body = rows[1]["content"]
    assert body[0]["type"] == "tableCell"
    assert body[0]["content"][0]["content"][0]["text"] == "one"


def test_markdown_to_adf_tracking_style_table() -> None:
    """GFM table with **Tracking** heading + event rows (Jira ADF table nodes)."""
    md = """**Tracking**

| When it Fires (Trigger) | Event Name (ID) | Required Properties (Meta) |
|--------------------------|-----------------|----------------------------|
| Notification displayed | `notification_shown` | type, message, timestamp, source_action |
| Notification dismissed | `notification_dismissed` | type, dismiss_method, display_duration |
| Auto-dismiss timer expires | `notification_auto_dismissed` | type, display_duration |
| Error notification action clicked | `notification_action_clicked` | error_type, action_taken |
"""
    doc = markdown_to_adf(md)
    assert doc["content"][0]["type"] == "paragraph"
    assert doc["content"][1]["type"] == "table"
    tbl = doc["content"][1]
    assert len(tbl["content"]) == 5
    first_body = tbl["content"][1]["content"][1]["content"][0]["content"][0]["text"]
    assert "notification_shown" in first_body


def test_adf_table_round_trip() -> None:
    md = "| A | B |\n|---|---|\n| c | d |\n"
    doc = markdown_to_adf(md)
    back = adf_to_markdown(doc)
    assert "| A | B |" in back
    assert "|---|" in back or "| --- |" in back
    assert "c" in back and "d" in back


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


def test_description_from_jira_api_property_holder_like_jira_client() -> None:
    """python-jira parses ADF JSON into PropertyHolder; must not use str() (~56-char repr)."""
    adf_json = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Full epic body from Jira Cloud."}],
            }
        ],
    }
    ph = dict2resource(adf_json)
    assert str(ph).startswith("<jira.resources.PropertyHolder")
    out = description_from_jira_api(ph)
    assert "Full epic body" in out
    assert len(out) > 20


def test_adf_hard_break_in_paragraph() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Line A"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "Line B"},
                ],
            }
        ],
    }
    assert adf_to_markdown(doc) == "Line A\nLine B"


def test_adf_nested_bullet_list() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Outer"}],
                            },
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {
                                                "type": "paragraph",
                                                "content": [{"type": "text", "text": "Inner"}],
                                            }
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    out = adf_to_markdown(doc)
    assert "Outer" in out
    assert "Inner" in out


def test_adf_unknown_block_collects_text_fallback() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "extension",
                "attrs": {"extensionType": "com.atlassian.x"},
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "From extension"}]}
                ],
            }
        ],
    }
    assert "From extension" in adf_to_markdown(doc)


def test_adf_inline_emoji_mention_card_date() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "emoji", "attrs": {"text": "🚀", "shortName": ":rocket:"}},
                    {"type": "mention", "attrs": {"text": "@alice", "id": "acc-1"}},
                    {"type": "inlineCard", "attrs": {"url": "https://example.com"}},
                    {"type": "date", "attrs": {"timestamp": "2026-03-31"}},
                ],
            }
        ],
    }
    out = adf_to_markdown(doc)
    assert "🚀" in out
    assert "@alice" in out
    assert "https://example.com" in out
    assert "2026-03-31" in out


def test_adf_top_level_ordered_list() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "orderedList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "First"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Second"}],
                            }
                        ],
                    },
                ],
            }
        ],
    }
    out = adf_to_markdown(doc)
    assert "1. First" in out
    assert "2. Second" in out


def test_adf_bullet_nested_ordered_list() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "orderedList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {
                                                "type": "paragraph",
                                                "content": [{"type": "text", "text": "Sub"}],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    assert "Sub" in adf_to_markdown(doc)


def test_adf_list_item_heading_and_blockquote() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "heading",
                                "attrs": {"level": 3},
                                "content": [{"type": "text", "text": "Subhead"}],
                            },
                            {
                                "type": "blockquote",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Quoted"}],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    out = adf_to_markdown(doc)
    assert "Subhead" in out
    assert "Quoted" in out


def test_adf_rule_blockquote_top_level() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "rule"},
            {
                "type": "blockquote",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Quote line"}],
                    }
                ],
            },
        ],
    }
    out = adf_to_markdown(doc)
    assert "---" in out
    assert "Quote line" in out


def test_adf_panel_expand_media_and_attrs_fallback() -> None:
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "panel",
                "attrs": {"extensionType": "x"},
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "In panel"}]}
                ],
            },
            {
                "type": "expand",
                "attrs": {"title": "More"},
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Hidden"}]}
                ],
            },
            {"type": "nestedExpand", "attrs": {}},
            {"type": "mediaSingle", "content": []},
            {
                "type": "customBlock",
                "attrs": {"alt": "Alt text", "label": "Label"},
                "content": [{"type": "text", "text": "Body"}],
            },
        ],
    }
    out = adf_to_markdown(doc)
    assert "In panel" in out
    assert "Hidden" in out
    assert "Alt text" in out or "Label" in out or "Body" in out


def test_adf_paragraph_plus_bullet_list_newsletter_style() -> None:
    """Simulates Jira Cloud rich text: intro + bullets (like Discovery epic input)."""
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Users should be able to subscribe to a newsletter on the website.",
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "The system should provide a simple form where users "
                            "can enter their email."
                        ),
                    }
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Validate the email format"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Store the email in a database",
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        ],
    }
    out = adf_to_markdown(doc)
    assert len(out) > 200
    assert "newsletter" in out
    assert "Validate the email" in out
    assert "Store the email" in out
