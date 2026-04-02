from __future__ import annotations

from bmad_orchestrator.cli import _md_table_cell, _token_report_as_jira_markdown
from bmad_orchestrator.utils.jira_adf import markdown_to_adf


class _FakeClaude:
    def __init__(self, report: dict[str, object]) -> None:
        self._report = report

    def get_usage_report(self) -> dict[str, object]:
        return self._report


def test_md_table_cell_escapes_pipe() -> None:
    assert _md_table_cell("a|b") == "a·b"


def test_token_report_jira_markdown_single_model() -> None:
    report = {
        "models_mixed": False,
        "model": "claude-sonnet-4-20250514",
        "rows": [
            {
                "agent": "Winston (Architect)",
                "calls": 1,
                "input_tokens": 2106,
                "output_tokens": 636,
                "total_tokens": 2742,
                "duration_s": 13.67,
                "model": "claude-sonnet-4-20250514",
            },
        ],
        "total_input": 2106,
        "total_output": 636,
        "total": 2742,
        "total_calls": 1,
        "total_duration_s": 13.67,
    }
    md = _token_report_as_jira_markdown(_FakeClaude(report))
    assert "## Token Usage" in md
    assert "**Model:** claude-sonnet-4-20250514" in md
    assert "| Step | Input | Output | Total | Calls | Time |" in md
    assert "| Winston (Architect) | 2,106 | 636 | 2,742 | 1 | 13.7s |" in md
    assert "| **Total** | 2,106 | 636 | 2,742 | 1 | 13.67s |" in md
    doc = markdown_to_adf(md)
    assert any(b.get("type") == "table" for b in doc.get("content") or [])


def test_token_report_jira_markdown_mixed_models() -> None:
    report = {
        "models_mixed": True,
        "model": "claude-3-5-sonnet",
        "rows": [
            {
                "agent": "Agent A",
                "calls": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "duration_s": 1.0,
                "model": "model-a",
            },
            {
                "agent": "Agent B",
                "calls": 2,
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
                "duration_s": 2.5,
                "model": "model-b",
            },
        ],
        "total_input": 30,
        "total_output": 15,
        "total": 45,
        "total_calls": 3,
        "total_duration_s": 3.5,
    }
    md = _token_report_as_jira_markdown(_FakeClaude(report))
    assert "**Model:**" not in md
    assert "| Step | Model | Input | Output | Total | Calls | Time |" in md
    assert "| Agent A | model-a |" in md
    assert "| **Total** | | 30 | 15 | 45 | 3 | 3.50s |" in md
    doc = markdown_to_adf(md)
    tables = [b for b in (doc.get("content") or []) if b.get("type") == "table"]
    assert len(tables) == 1
    assert len(tables[0]["content"]) == 4


def test_token_report_jira_markdown_empty_rows() -> None:
    report = {
        "models_mixed": False,
        "model": "x",
        "rows": [],
        "total_input": 0,
        "total_output": 0,
        "total": 0,
        "total_calls": 0,
        "total_duration_s": 0.0,
    }
    assert _token_report_as_jira_markdown(_FakeClaude(report)) == ""
