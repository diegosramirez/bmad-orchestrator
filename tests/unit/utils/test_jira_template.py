from __future__ import annotations

from pathlib import Path

from bmad_orchestrator.utils.jira_template import (
    JIRA_TEMPLATE_SECTIONS,
    load_template,
    matches_template,
    normalise_discovery_epic_headings,
    normalise_epic_architect_headings,
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


# ── normalise_discovery_epic_headings ────────────────────────────────────────

def test_normalise_discovery_empty():
    assert normalise_discovery_epic_headings("") == ""


def test_normalise_discovery_strips_number_and_hashes():
    raw = "1. 📖 Overview\n\nBody here."
    result = normalise_discovery_epic_headings(raw)
    assert result.splitlines()[0] == "\u200B**📖 Overview**"
    assert "Body here." in result


def test_normalise_discovery_hash_heading():
    raw = "# 🎯 Goals\n\n- One"
    result = normalise_discovery_epic_headings(raw)
    assert result.splitlines()[0] == "\u200B**🎯 Goals**"


def test_normalise_discovery_epic_title_line():
    raw = "1. 🧩 User Registration with Email and Password"
    assert normalise_discovery_epic_headings(raw) == (
        "\u200B**🧩 User Registration with Email and Password**"
    )


def test_normalise_discovery_idempotent_with_zwsp_bold():
    line = "\u200B**📖 Overview**"
    assert normalise_discovery_epic_headings(line) == line


def test_normalise_discovery_unwraps_bold_then_wraps_zwsp():
    raw = "**👤 User Value**"
    assert normalise_discovery_epic_headings(raw) == "\u200B**👤 User Value**"


def test_normalise_discovery_preserves_non_headings():
    raw = "- User can sign in\nStill a bullet line"
    assert normalise_discovery_epic_headings(raw) == raw


def test_normalise_discovery_chained_with_jira_normalise():
    # As in create_or_correct_epic: jira first, then discovery
    raw = "1. 📖 Overview\n\nText"
    step1 = normalise_jira_headings(raw)
    step2 = normalise_discovery_epic_headings(step1)
    assert step2.splitlines()[0] == "\u200B**📖 Overview**"


# ── normalise_epic_architect_headings ────────────────────────────────────────

def test_normalise_epic_architect_empty():
    assert normalise_epic_architect_headings("") == ""


def test_normalise_epic_architect_strips_roman_outline():
    raw = "i. Architecture Overview\n\nBody."
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "\u200B**Architecture Overview**"
    assert "Body." in result


def test_normalise_epic_architect_strips_letter_outline():
    raw = "a. Epic Architect\n\nNote"
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "\u200B**Epic Architect**"


def test_normalise_epic_architect_hash_heading():
    raw = "### System Components\n- A"
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "\u200B**System Components**"


def test_normalise_epic_architect_idempotent_zwsp():
    line = "\u200B**Data Flow**"
    assert normalise_epic_architect_headings(line) == line


def test_normalise_epic_architect_preserves_non_headings():
    raw = "- Router calls service layer\nPlain line"
    assert normalise_epic_architect_headings(raw) == raw


def test_normalise_epic_architect_chained_after_jira():
    raw = "1. a. i. Architecture Overview\n\ntext"
    step1 = normalise_jira_headings(raw)
    step2 = normalise_epic_architect_headings(step1)
    assert step2.splitlines()[0] == "\u200B**Architecture Overview**"


def test_normalise_epic_architect_preserves_merge_heading():
    raw = "## Epic Architect\n\ni. Architecture Overview"
    out = normalise_epic_architect_headings(raw)
    lines = out.splitlines()
    assert lines[0] == "## Epic Architect"
    assert lines[2] == "\u200B**Architecture Overview**"
