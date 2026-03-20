from __future__ import annotations

import importlib.resources
from functools import cache
from pathlib import Path

import yaml

# Personas bundled inside the installed package (via pyproject.toml force-include)
try:
    _BUNDLED_PERSONAS_DIR: Path | None = Path(
        str(importlib.resources.files("bmad_orchestrator") / "personas" / "data")
    )
except Exception:
    _BUNDLED_PERSONAS_DIR = None

# ── Mapping from logical agent ID to the expected YAML filename ───────────────
AGENT_FILE_MAP: dict[str, list[str]] = {
    "architect":    ["architect.agent.yaml", "architect.yaml"],
    "designer":     ["ux-designer.agent.yaml", "ux-designer.yaml", "designer.yaml"],
    "developer":    ["dev.agent.yaml", "developer.agent.yaml", "dev.yaml"],
    "qa":           ["qa.agent.yaml", "qa.yaml"],
    "e2e_tester":   ["qa.agent.yaml", "qa.yaml"],
    "scrum_master": ["sm.agent.yaml", "scrum-master.agent.yaml", "sm.yaml"],
    "pm":           ["pm.agent.yaml", "product-manager.agent.yaml", "pm.yaml"],
}

# ── Human-readable display names for console logging ─────────────────────────
AGENT_DISPLAY_NAMES: dict[str, str] = {
    "architect": "Winston (Architect)",
    "architect_party": "Winston (Architect — Party Mode)",
    "designer": "Sally (Designer)",
    "developer": "Amelia (Developer)",
    "developer_party": "Amelia (Developer — Party Mode)",
    "qa": "Quinn (QA)",
    "e2e_tester": "Quinn (E2E Tester)",
    "scrum_master": "Bob (Scrum Master)",
    "pm": "Alex (PM)",
    "build-expert": "Build Expert",
}

# ── Fallback personas when BMAD files are not installed ───────────────────────
FALLBACK_PERSONAS: dict[str, str] = {
    "architect": (
        "You are Winston, a pragmatic Senior System Architect with 15+ years of experience. "
        "You design scalable, maintainable systems with a focus on clean architecture. "
        "You provide structured technical reviews with concrete improvement recommendations. "
        "You always consider security, performance, and maintainability tradeoffs."
    ),
    "designer": (
        "You are Sally, an empathetic UX Designer who bridges user needs "
        "and technical constraints. "
        "You think in user flows, edge cases, and accessibility. "
        "You produce clear wireframe descriptions and interaction patterns in text form."
    ),
    "developer": (
        "You are Amelia, a Senior Software Engineer known for clean, well-tested code. "
        "You implement features methodically, covering edge cases and writing "
        "self-documenting code. "
        "You flag technical debt honestly and propose pragmatic solutions."
    ),
    "qa": (
        "You are Quinn, a pragmatic QA Engineer who thinks adversarially. "
        "You design test cases covering happy paths, edge cases, and failure modes. "
        "You write thorough automated tests with clear assertions and good coverage."
    ),
    "e2e_tester": (
        "You are Quinn, a QA Engineer specializing in end-to-end browser testing "
        "with Playwright. You write E2E tests that validate real user workflows "
        "using semantic locators (getByRole, getByLabel, getByText). You focus on "
        "testing user interactions (navigation, form submission, data display) and "
        "asserting visible outcomes. Keep tests linear, deterministic, and "
        "independent. Use the webServer option in playwright.config.ts to "
        "auto-start the dev server."
    ),
    "scrum_master": (
        "You are Bob, a Technical Scrum Master who writes clear, actionable user stories. "
        "You enforce INVEST criteria "
        "(Independent, Negotiable, Valuable, Estimable, Small, Testable). "
        "You ensure acceptance criteria are unambiguous and verifiable."
    ),
    "pm": (
        "You are Alex, a Product Manager who distills user needs into clear epics and stories. "
        "You write concise problem statements, define success metrics, and prioritize effectively. "
        "You ensure work aligns with business goals."
    ),
}


def _find_agent_file(agent_id: str, search_dir: Path) -> Path | None:
    """Search search_dir recursively for a BMAD agent YAML file."""
    candidates = AGENT_FILE_MAP.get(agent_id, [])
    for filename in candidates:
        for found in search_dir.rglob(filename):
            if found.is_file():
                return found
    return None


def _parse_agent_yaml(path: Path) -> str:
    """Parse a BMAD agent YAML and return a formatted system prompt string."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    parts: list[str] = []

    name = data.get("name") or data.get("title", "")
    if name:
        parts.append(f"Name: {name}")

    persona = data.get("persona", {})
    if isinstance(persona, dict):
        for key in ("role", "identity", "principles", "communication_style"):
            val = persona.get(key)
            if val:
                parts.append(f"{key.replace('_', ' ').title()}: {val}")
    elif isinstance(persona, str):
        parts.append(persona)

    critical = data.get("critical_actions") or data.get("critical_instructions")
    if critical:
        parts.append(f"Critical Actions: {critical}")

    return "\n".join(parts) if parts else str(data)


@cache
def load_persona(agent_id: str, bmad_install_dir: str) -> str:
    """
    Load a BMAD agent persona from installed YAML files or fall back to a
    hardcoded minimal persona.

    Search order:
      1. Bundled package data (installed via wheel, always available)
      2. CWD-relative bmad_install_dir (.claude/ in the project or target repo)
      3. Hardcoded fallback personas

    Results are cached after the first call per (agent_id, bmad_install_dir).
    """
    # 1. Bundled package data (populated at wheel build time via force-include)
    if _BUNDLED_PERSONAS_DIR is not None and _BUNDLED_PERSONAS_DIR.exists():
        found = _find_agent_file(agent_id, _BUNDLED_PERSONAS_DIR)
        if found:
            try:
                return _parse_agent_yaml(found)
            except Exception:
                pass

    # 2. CWD-relative install dir (e.g. .claude/commands/ when running from source)
    search_dir = Path(bmad_install_dir)
    if search_dir.exists():
        found = _find_agent_file(agent_id, search_dir)
        if found:
            try:
                return _parse_agent_yaml(found)
            except Exception:
                pass

    # 3. Hardcoded fallback
    return FALLBACK_PERSONAS.get(
        agent_id,
        f"You are a helpful AI assistant acting as the {agent_id} role.",
    )


def build_system_prompt(agent_id: str, bmad_install_dir: str) -> str:
    """Return a complete system prompt for the given BMAD agent persona."""
    persona = load_persona(agent_id, bmad_install_dir)
    return (
        f"<persona>\n{persona}\n</persona>\n\n"
        "You are operating as part of an autonomous engineering orchestrator. "
        "Always respond in the structured format requested. "
        "Be precise, concrete, and actionable."
    )
