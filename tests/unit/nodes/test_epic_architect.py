from __future__ import annotations

from bmad_orchestrator.nodes.epic_architect import (
    ARCH_HEADING,
    LEGACY_ARCH_HEADING,
    ArchitectureBlockResult,
    make_epic_architect_node,
    merge_epic_architect_description,
)
from tests.conftest import make_state


def test_merge_epic_architect_appends_when_missing() -> None:
    base = "# Discovery\n\n# Overview\nHello."
    out = merge_epic_architect_description(base, "- A\n- B")
    assert ARCH_HEADING in out
    assert "- A" in out
    assert "Hello" in out


def test_merge_epic_architect_replaces_existing_block() -> None:
    base = f"# Discovery\n\n{LEGACY_ARCH_HEADING}\n\nold\n\n# Next\nx"
    out = merge_epic_architect_description(base, "new body")
    assert "new body" in out
    assert "old" not in out
    assert "# Next" in out


def test_merge_epic_architect_replaces_hash_architecture() -> None:
    base = f"# Discovery\n\n{ARCH_HEADING}\n\nold block\n"
    out = merge_epic_architect_description(base, "fresh")
    assert "fresh" in out
    assert "old block" not in out


def test_merge_epic_architect_fence_ignores_hash_inside_code() -> None:
    """H1 line inside a fenced block must not end the Architecture section early."""
    base = (
        f"# Discovery\n\n{ARCH_HEADING}\n\n```text\n# not a heading\n```\n\n"
        "# After Section\nTail."
    )
    out = merge_epic_architect_description(base, "replacement body")
    assert "replacement body" in out
    assert "# Discovery" in out
    assert ARCH_HEADING in out
    assert "# After Section" in out
    assert "# not a heading" not in out


def test_epic_architect_aborts_without_discovery_marker(settings, mock_jira, mock_claude):
    mock_jira.get_epic.return_value = {
        "summary": "S",
        "description": "no discovery heading here",
    }
    node = make_epic_architect_node(mock_claude, mock_jira, settings)
    result = node(make_state(current_epic_id="EP-1"))
    mock_claude.complete_structured.assert_not_called()
    mock_jira.update_epic.assert_not_called()
    assert "Discovery" in result["execution_log"][0]["message"]


def test_epic_architect_updates_jira(settings, mock_jira, mock_claude):
    mock_jira.get_epic.return_value = {
        "summary": "Login",
        "description": "# Discovery\n\n## Goals\nx",
    }
    mock_claude.complete_structured.return_value = ArchitectureBlockResult(
        architecture_block="## Architecture Overview\n- One",
    )
    arch = settings.model_copy(update={"execution_mode": "epic_architect"})
    node = make_epic_architect_node(mock_claude, mock_jira, arch)
    result = node(make_state(current_epic_id="EP-2"))

    mock_jira.update_epic.assert_called_once()
    call = mock_jira.update_epic.call_args
    assert call[0][0] == "EP-2"
    desc = call[0][1]["description"]
    assert ARCH_HEADING in desc
    assert "Architecture Overview" in desc
    assert result.get("architect_output")


def test_epic_architect_missing_epic_key(settings, mock_jira, mock_claude):
    node = make_epic_architect_node(mock_claude, mock_jira, settings)
    result = node(make_state(current_epic_id=None))
    assert "missing" in result["execution_log"][0]["message"].lower()
    mock_jira.get_epic.assert_not_called()
