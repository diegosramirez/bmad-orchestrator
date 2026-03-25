from __future__ import annotations

from bmad_orchestrator.utils.discovery_epic_prompt import DISCOVERY_EPIC_PROMPT_FINAL


def test_discovery_prompt_contains_validation_and_structure_markers() -> None:
    text = DISCOVERY_EPIC_PROMPT_FINAL
    assert "STEP 1" in text and "VALIDATE INPUT" in text
    assert "STEP 2" in text and "GENERATE EPIC" in text
    assert "Overview" in text or "📖" in text
    assert "Goals" in text
    assert "Scope" in text
    assert "Not enough information to run Discovery" in text
    assert "insufficient_info_message" in text or "JSON" in text
