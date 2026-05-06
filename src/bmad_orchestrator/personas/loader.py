from __future__ import annotations

import importlib.resources
import re
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

# ── Mapping from logical agent ID to expected source-file candidates ──────────
# v6.6+ stores persona content in SKILL.md (markdown w/ YAML frontmatter);
# v6.2-v6.5 used bmad-skill-manifest.yaml; older installs used legacy names.
# Listed in preference order (first match wins).
AGENT_FILE_MAP: dict[str, list[str]] = {
    "architect":    ["SKILL.md", "bmad-skill-manifest.yaml",
                     "architect.agent.yaml", "architect.yaml"],
    "designer":     ["SKILL.md", "bmad-skill-manifest.yaml",
                     "ux-designer.agent.yaml", "ux-designer.yaml"],
    "developer":    ["SKILL.md", "bmad-skill-manifest.yaml",
                     "dev.agent.yaml", "developer.agent.yaml"],
    "qa":           ["SKILL.md", "bmad-skill-manifest.yaml",
                     "qa.agent.yaml", "qa.yaml"],
    "e2e_tester":   ["SKILL.md", "bmad-skill-manifest.yaml",
                     "qa.agent.yaml", "qa.yaml"],
    "scrum_master": ["SKILL.md", "bmad-skill-manifest.yaml",
                     "sm.agent.yaml", "scrum-master.agent.yaml"],
    "pm":           ["SKILL.md", "bmad-skill-manifest.yaml",
                     "pm.agent.yaml", "product-manager.agent.yaml"],
}

# v6.2+ skill directory names containing the agent manifest for each persona.
# Used to disambiguate when multiple bmad-skill-manifest.yaml files exist.
# v6.3+: bmad-agent-qa, bmad-agent-sm, bmad-agent-quick-flow-solo-dev were
# consolidated into bmad-agent-dev (Amelia).
_AGENT_SKILL_DIRS: dict[str, str] = {
    "architect":    "bmad-agent-architect",
    "designer":     "bmad-agent-ux-designer",
    "developer":    "bmad-agent-dev",
    "qa":           "bmad-agent-dev",
    "e2e_tester":   "bmad-agent-dev",
    "scrum_master": "bmad-agent-dev",
    "pm":           "bmad-agent-pm",
}

# ── Human-readable display names for console logging ─────────────────────────
AGENT_DISPLAY_NAMES: dict[str, str] = {
    "architect": "Winston (Architect)",
    "architect_party": "Winston (Architect — Party Mode)",
    "designer": "Sally (Designer)",
    "developer": "Amelia (Developer)",
    "developer_party": "Amelia (Developer — Party Mode)",
    "qa": "Amelia (Developer — QA Mode)",
    "e2e_tester": "Amelia (Developer — E2E Mode)",
    "scrum_master": "Amelia (Developer — SM Mode)",
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
    """Search search_dir recursively for a BMAD agent persona source file.

    For ``SKILL.md`` (v6.6+) and ``bmad-skill-manifest.yaml`` (v6.2-v6.5), only
    match when the file lives inside the expected skill directory for this
    agent_id — many other skills also ship these filenames and we don't want
    to pick up the wrong one.
    """
    expected_dir = _AGENT_SKILL_DIRS.get(agent_id)
    candidates = AGENT_FILE_MAP.get(agent_id, [])
    for filename in candidates:
        scoped_to_skill_dir = filename in ("SKILL.md", "bmad-skill-manifest.yaml")
        for found in search_dir.rglob(filename):
            if not found.is_file():
                continue
            if scoped_to_skill_dir and expected_dir and found.parent.name != expected_dir:
                continue
            return found
    return None


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n(.*)$", re.DOTALL)


def _parse_skill_md(path: Path) -> str:
    """Parse a v6.6+ ``SKILL.md`` and return a formatted system prompt string.

    Extracts the H1 title and the ``## Overview`` section body — the rest of
    the file is BMAD activation/customization boilerplate that's specific to
    running inside Claude Code's skill harness, not persona content.
    """
    text = path.read_text(encoding="utf-8")
    body = text
    match = _FRONTMATTER_RE.match(text)
    if match:
        body = match.group(2)

    parts: list[str] = []
    title_match = re.search(r"^#\s+(.+?)$", body, re.MULTILINE)
    if title_match:
        parts.append(f"Name: {title_match.group(1).strip()}")

    # Capture the "## Overview" section up to the next H2 (or EOF).
    overview_match = re.search(
        r"^##\s+Overview\s*\n(.*?)(?=^##\s|\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if overview_match:
        parts.append(overview_match.group(1).strip())

    return "\n\n".join(parts) if parts else body.strip()


def _parse_agent_yaml(path: Path) -> str:
    """Parse a BMAD agent persona file and return a system prompt string.

    Dispatches by file type:
    - ``SKILL.md`` (v6.6+) — markdown with YAML frontmatter; persona is the
      H1 title + ``## Overview`` section.
    - ``bmad-skill-manifest.yaml`` (v6.2-v6.5) — flat YAML manifest with
      ``displayName``, ``role``, ``identity``, ``communicationStyle``,
      ``principles`` at top level.
    - Legacy ``*.agent.yaml`` — nested ``persona`` dict.
    """
    if path.name == "SKILL.md":
        return _parse_skill_md(path)

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    parts: list[str] = []

    # v6.2+ flat manifest format (bmad-skill-manifest.yaml)
    if "displayName" in data or "communicationStyle" in data:
        display = data.get("displayName") or data.get("title", "")
        if display:
            parts.append(f"Name: {display}")
        for key in ("role", "identity", "principles", "communicationStyle"):
            val = data.get(key)
            if val:
                label = "Communication Style" if key == "communicationStyle" else key.title()
                parts.append(f"{label}: {val}")
        return "\n".join(parts) if parts else str(data)

    # Legacy nested format
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

    # 2. CWD-relative install dir (e.g. .claude/skills/ when running from source)
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
