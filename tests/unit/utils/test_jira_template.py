from __future__ import annotations

from pathlib import Path

from bmad_orchestrator.utils.jira_template import (
    JIRA_TEMPLATE_SECTIONS,
    load_template,
    matches_template,
    normalise_jira_headings,
)

# ── load_template ────────────────────────────────────────────────────────────

def test_load_template_returns_content_when_file_exists(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    template = docs / "template-jira.md"
    template.write_text("# Template\nHello")
    assert load_template(tmp_path) == "# Template\nHello"


def test_load_template_returns_empty_when_missing(tmp_path: Path):
    assert load_template(tmp_path) == ""


def test_load_template_returns_empty_on_read_error(tmp_path: Path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    template = docs / "template-jira.md"
    template.write_text("content")

    def _raise(*a, **kw):
        raise OSError("read failed")

    monkeypatch.setattr(Path, "read_text", _raise)
    assert load_template(tmp_path) == ""


# ── matches_template ─────────────────────────────────────────────────────────

def test_matches_template_true_when_all_sections_present():
    content = "\n".join(JIRA_TEMPLATE_SECTIONS) + "\nExtra content"
    assert matches_template(content) is True


def test_matches_template_false_when_empty():
    assert matches_template("") is False
    assert matches_template("   ") is False


def test_matches_template_false_when_section_missing():
    # Omit **Tracking**
    content = "\n".join(s for s in JIRA_TEMPLATE_SECTIONS if s != "**Tracking**")
    assert matches_template(content) is False


# ── normalise_jira_headings ──────────────────────────────────────────────────

def test_normalise_empty_content():
    assert normalise_jira_headings("") == ""


def test_normalise_strips_outline_prefix_from_known_section():
    result = normalise_jira_headings("1. Hypothesis")
    assert result == "\u200B**Hypothesis**"


def test_normalise_strips_nested_outline_prefixes():
    result = normalise_jira_headings("1. a. i. Hypothesis")
    assert result == "\u200B**Hypothesis**"


def test_normalise_standalone_section_name():
    result = normalise_jira_headings("Acceptance Criteria")
    assert result == "\u200B**Acceptance Criteria**"


def test_normalise_standalone_section_with_colon():
    result = normalise_jira_headings("Tracking:")
    assert result == "\u200B**Tracking**"


def test_normalise_outline_only_becomes_blank():
    result = normalise_jira_headings("1.")
    assert result == ""


def test_normalise_unknown_label_after_prefix():
    result = normalise_jira_headings("1. Some random label")
    assert result == "Some random label"


def test_normalise_preserves_plain_text():
    result = normalise_jira_headings("Just some content here")
    assert result == "Just some content here"


def test_normalise_multiple_lines():
    content = "1. Hypothesis\nSome body text\n2. Intervention\n- bullet"
    result = normalise_jira_headings(content)
    lines = result.splitlines()
    assert lines[0] == "\u200B**Hypothesis**"
    assert lines[1] == "Some body text"
    assert lines[2] == "\u200B**Intervention**"
    assert lines[3] == "- bullet"
