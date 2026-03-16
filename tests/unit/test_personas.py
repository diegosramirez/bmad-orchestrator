from __future__ import annotations

from bmad_orchestrator.personas.loader import (
    FALLBACK_PERSONAS,
    _parse_agent_yaml,
    build_system_prompt,
    load_persona,
)


def test_fallback_returned_when_install_dir_missing():
    result = load_persona("architect", "/nonexistent/path")
    assert result == FALLBACK_PERSONAS["architect"]


def test_fallback_returned_for_unknown_agent():
    result = load_persona("unknown-agent", "/nonexistent/path")
    assert "unknown-agent" in result


def test_build_system_prompt_wraps_persona():
    result = build_system_prompt("developer", "/nonexistent")
    assert "<persona>" in result
    assert FALLBACK_PERSONAS["developer"] in result
    assert "autonomous engineering orchestrator" in result


def test_all_fallback_personas_are_non_empty():
    for agent_id, persona in FALLBACK_PERSONAS.items():
        assert len(persona) > 20, f"Persona for {agent_id} is too short"


def test_load_persona_cached(tmp_path):
    """Second call with same args returns cached result (no file I/O)."""
    load_persona.cache_clear()
    r1 = load_persona("qa", str(tmp_path))
    r2 = load_persona("qa", str(tmp_path))
    assert r1 is r2  # same object == cached


def test_load_persona_reads_yaml_file(tmp_path):
    """load_persona reads from a YAML file when bmad_install_dir exists."""
    load_persona.cache_clear()
    yaml_content = "name: TestArchitect\npersona:\n  role: Senior Architect\n"
    (tmp_path / "architect.agent.yaml").write_text(yaml_content)
    result = load_persona("architect", str(tmp_path))
    assert "Senior Architect" in result or "TestArchitect" in result
    load_persona.cache_clear()


def test_parse_agent_yaml_with_dict_persona(tmp_path):
    path = tmp_path / "arch.yaml"
    path.write_text(
        "name: Winston\npersona:\n  role: Architect\n  identity: A helpful AI\n"
        "critical_actions: Always write tests\n"
    )
    result = _parse_agent_yaml(path)
    assert "Architect" in result
    assert "Always write tests" in result


def test_parse_agent_yaml_with_string_persona(tmp_path):
    path = tmp_path / "dev.yaml"
    path.write_text("name: Amelia\npersona: I write clean code\n")
    result = _parse_agent_yaml(path)
    assert "clean code" in result


def test_load_persona_falls_back_on_parse_error(tmp_path):
    """If YAML parsing fails, fall back to hardcoded persona."""
    load_persona.cache_clear()
    (tmp_path / "architect.agent.yaml").write_text(": invalid: yaml: {{{")
    result = load_persona("architect", str(tmp_path))
    assert len(result) > 20  # got fallback, not empty
    load_persona.cache_clear()
