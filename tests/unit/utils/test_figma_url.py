from __future__ import annotations

import pytest

from bmad_orchestrator.utils.figma_url import extract_figma_url


@pytest.mark.parametrize(
    "text,expected",
    [
        (None, None),
        ("", None),
        ("No links at all", None),
        (
            "See design: https://www.figma.com/design/abc123/Example-File",
            "https://www.figma.com/design/abc123/Example-File",
        ),
        (
            "Link: https://figma.com/file/XYZ789 for context",
            "https://figma.com/file/XYZ789",
        ),
        (
            "Proto: http://www.figma.com/proto/abc123/Flow?node-id=12-34",
            "http://www.figma.com/proto/abc123/Flow?node-id=12-34",
        ),
        (
            "Board: https://www.figma.com/board/boardId/Kickoff",
            "https://www.figma.com/board/boardId/Kickoff",
        ),
        (
            "Markdown [link](https://www.figma.com/design/ABC/Home) here",
            "https://www.figma.com/design/ABC/Home",
        ),
    ],
)
def test_extract_figma_url(text: str | None, expected: str | None) -> None:
    assert extract_figma_url(text) == expected


def test_extract_returns_first_match_when_multiple() -> None:
    text = (
        "Primary https://www.figma.com/design/AAA/One "
        "secondary https://www.figma.com/design/BBB/Two"
    )
    assert extract_figma_url(text) == "https://www.figma.com/design/AAA/One"


def test_extract_ignores_non_figma_urls() -> None:
    text = "https://example.com/figma/fake https://not-figma.com/design/abc"
    assert extract_figma_url(text) is None
