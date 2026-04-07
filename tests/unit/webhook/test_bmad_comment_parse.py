"""Tests for ``parse_bmad_comment_command`` (Jira /bmad retry|refine parsing)."""
from __future__ import annotations

import pytest

from bmad_orchestrator.webhook.bmad_comment_parse import parse_bmad_comment_command


@pytest.mark.parametrize(
    ("text", "expected_guidance"),
    [
        ("/bmad refine", ""),
        ("/bmad retry", ""),
        ("/bmad refine fix auth", "fix auth"),
        ("/bmad RETRY one two", "one two"),
        ("/bmad refine \"hello world\"", "hello world"),
        (
            "/bmad refine \"line1\nline2\"",
            "line1\nline2",
        ),
        (
            '/bmad refine "Fix route.\nEnsure tests pass."',
            "Fix route.\nEnsure tests pass.",
        ),
        (
            "/bmad refine line one\nline two\nline three",
            "line one\nline two\nline three",
        ),
        (
            "/bmad refine \u201cFix the bug\u201d",
            "Fix the bug",
        ),
    ],
)
def test_parse_bmad_comment_success(text: str, expected_guidance: str) -> None:
    sub, guidance, err = parse_bmad_comment_command(text)
    assert err is None
    assert sub in ("retry", "refine")
    assert guidance == expected_guidance


def test_parse_bmad_not_bmad() -> None:
    sub, guidance, err = parse_bmad_comment_command("hello")
    assert sub is None
    assert guidance == ""
    assert err == "not_bmad"


def test_parse_unknown_subcommand() -> None:
    sub, guidance, err = parse_bmad_comment_command("/bmad deploy stuff")
    assert sub is None
    assert guidance == ""
    assert err == "Unknown /bmad subcommand: deploy"


def test_parse_usage_when_empty_after_bmad() -> None:
    sub, guidance, err = parse_bmad_comment_command("/bmad")
    assert sub is None
    assert guidance == ""
    assert "Usage:" in (err or "")


def test_parse_usage_when_only_slash_bmad_whitespace() -> None:
    sub, guidance, err = parse_bmad_comment_command("/bmad   ")
    assert sub is None
    assert guidance == ""
    assert "Usage:" in (err or "")
