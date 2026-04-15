from __future__ import annotations

from pathlib import Path

from bmad_orchestrator.utils.jira_template import (
    JIRA_TEMPLATE_SECTIONS,
    LEGACY_DISCOVERY_HTML_COMMENT,
    ensure_discovery_h1,
    epic_has_discovery_section,
    load_epic_template,
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


def test_load_epic_template_returns_content_when_file_exists(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    template = docs / "template-jira-epic.md"
    template.write_text("# Epic charter\nTerse")
    assert load_epic_template(tmp_path) == "# Epic charter\nTerse"


def test_load_epic_template_returns_empty_when_missing(tmp_path: Path):
    assert load_epic_template(tmp_path) == ""


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


# ── epic_has_discovery_section / ensure_discovery_h1 ─────────────────────────

def test_epic_has_discovery_section_h1_and_legacy() -> None:
    assert epic_has_discovery_section("# Discovery\n\nBody")
    assert epic_has_discovery_section("Intro\n\n# Discovery\n")
    assert not epic_has_discovery_section("# Discover\n")
    assert epic_has_discovery_section(f"{LEGACY_DISCOVERY_HTML_COMMENT}\nold")


def test_ensure_discovery_h1() -> None:
    assert ensure_discovery_h1("").strip() == "# Discovery"
    assert ensure_discovery_h1("# Discovery\n\nx") == "# Discovery\n\nx"
    out = ensure_discovery_h1("## Sub\n")
    assert out.startswith("# Discovery\n\n")


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
    assert result.splitlines()[0] == "## 📖 Overview"
    assert "Body here." in result


def test_normalise_discovery_hash_heading():
    raw = "# 🎯 Goals\n\n- One"
    result = normalise_discovery_epic_headings(raw)
    assert result.splitlines()[0] == "## 🎯 Goals"


def test_normalise_discovery_epic_title_line():
    raw = "1. 🧩 User Registration with Email and Password"
    assert normalise_discovery_epic_headings(raw) == (
        "## 🧩 User Registration with Email and Password"
    )


def test_normalise_discovery_preserves_discovery_h1():
    raw = "# Discovery\n\n## 📖 Overview\n\nText"
    lines = normalise_discovery_epic_headings(raw).splitlines()
    assert lines[0] == "# Discovery"
    assert lines[2] == "## 📖 Overview"


def test_normalise_discovery_idempotent_with_h2():
    line = "## 📖 Overview"
    assert normalise_discovery_epic_headings(line) == line


def test_normalise_discovery_unwraps_bold_to_h2():
    raw = "**👤 User Value**"
    assert normalise_discovery_epic_headings(raw) == "## 👤 User Value"


def test_normalise_discovery_preserves_non_headings():
    raw = "- User can sign in\nStill a bullet line"
    assert normalise_discovery_epic_headings(raw) == raw


def test_normalise_discovery_chained_with_jira_normalise():
    # As in create_or_correct_epic: jira first, then discovery
    raw = "1. 📖 Overview\n\nText"
    step1 = normalise_jira_headings(raw)
    step2 = normalise_discovery_epic_headings(step1)
    assert step2.splitlines()[0] == "## 📖 Overview"


# ── normalise_epic_architect_headings ────────────────────────────────────────

def test_normalise_epic_architect_empty():
    assert normalise_epic_architect_headings("") == ""


def test_normalise_epic_architect_strips_roman_outline():
    raw = "i. Architecture Overview\n\nBody."
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "## Architecture Overview"
    assert "Body." in result


def test_normalise_epic_architect_strips_roman_emoji_overview():
    raw = "i. 📖 Overview\n\nBody."
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "## 📖 Overview"
    assert "Body." in result


def test_normalise_epic_architect_strips_letter_outline():
    raw = "a. Epic Architect\n\nNote"
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "## Epic Architect"


def test_normalise_epic_architect_hash_heading():
    raw = "### System Components\n- A"
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "## System Components"


def test_normalise_epic_architect_hash_heading_emoji():
    raw = "### 🏗️ System Components\n- A"
    result = normalise_epic_architect_headings(raw)
    assert result.splitlines()[0] == "## 🏗️ System Components"


def test_normalise_epic_architect_idempotent_h2():
    line = "## Data Flow"
    assert normalise_epic_architect_headings(line) == line


def test_normalise_epic_architect_preserves_non_headings():
    raw = "- Router calls service layer\nPlain line"
    assert normalise_epic_architect_headings(raw) == raw


def test_normalise_epic_architect_chained_after_jira():
    raw = "1. a. i. Architecture Overview\n\ntext"
    step1 = normalise_jira_headings(raw)
    step2 = normalise_epic_architect_headings(step1)
    assert step2.splitlines()[0] == "## Architecture Overview"


def test_normalise_epic_architect_preserves_merge_heading():
    raw = "## Epic Architect\n\ni. Architecture Overview"
    out = normalise_epic_architect_headings(raw)
    lines = out.splitlines()
    assert lines[0] == "## Epic Architect"
    assert lines[2] == "## Architecture Overview"


def test_normalise_epic_architect_preserves_hash_architecture():
    raw = "# Architecture\n\n## System Components\n- A"
    lines = normalise_epic_architect_headings(raw).splitlines()
    assert lines[0] == "# Architecture"
    assert lines[2] == "## System Components"
