"""Interactive CLI prompts for epic selection and confirmations.

This module is ONLY used in cli.py before the graph starts.
It must NEVER be imported from LangGraph nodes.
"""
from __future__ import annotations

import re
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel

JIRA_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")

console = Console()

_NEW_EPIC_SENTINEL = "__create_new__"


def prompt_team_id() -> str:
    """Ask the user for a team identifier."""
    return questionary.text(
        "Team identifier (e.g. 'growth'):",
        validate=lambda v: len(v.strip()) > 0 or "Team ID cannot be empty",
    ).ask() or ""


def prompt_feature() -> str:
    """Ask the user for the feature description or Jira epic key."""
    return questionary.text(
        "Feature description or Jira epic key:",
        validate=lambda v: len(v.strip()) > 0 or "Prompt cannot be empty",
    ).ask() or ""


def is_jira_key(text: str) -> bool:
    """Return True if text looks like a Jira issue key (e.g. PUG-437)."""
    return bool(JIRA_KEY_PATTERN.match(text.strip()))


def display_epic(epic: dict[str, Any]) -> None:
    """Show a single epic in a Rich Panel."""
    desc = (epic.get("description") or "")[:200]
    console.print(
        Panel(
            f"[bold]Key:[/bold] {epic['key']}\n"
            f"[bold]Summary:[/bold] {epic['summary']}\n"
            f"[bold]Status:[/bold] {epic.get('status', 'N/A')}\n"
            f"[bold]Description:[/bold] {desc}",
            title=f"[bold blue]Epic {epic['key']}[/bold blue]",
        )
    )


def confirm_epic(epic: dict[str, Any]) -> bool:
    """Display an epic and ask the user to confirm using it."""
    display_epic(epic)
    return questionary.confirm(
        f"Use epic {epic['key']}?", default=True
    ).ask()


def select_epic_from_list(epics: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Present an arrow-key navigable list of epics and let the user pick one,
    or choose to create a new epic.

    Returns the chosen epic dict, or None if user chose "create new".
    """
    choices = []
    for epic in epics:
        label = f"{epic['key']} — {epic['summary']}"
        status = epic.get("status", "")
        if status:
            label += f" ({status})"
        choices.append(questionary.Choice(title=label, value=epic["key"]))

    choices.append(questionary.Choice(
        title="Create a new epic",
        value=_NEW_EPIC_SENTINEL,
    ))

    selected = questionary.select(
        "Select an epic:",
        choices=choices,
    ).ask()

    if selected is None or selected == _NEW_EPIC_SENTINEL:
        return None

    return next((e for e in epics if e["key"] == selected), None)


def confirm_action(action_description: str) -> bool:
    """Generic confirmation prompt for a described action."""
    return questionary.confirm(
        f"{action_description} Proceed?", default=True
    ).ask()


# ── Node descriptions for the skip-nodes checkbox ─────────────────────────

SKIPPABLE_NODES: list[tuple[str, str]] = [
    ("check_epic_state", "Validate epic status in Jira"),
    ("create_or_correct_epic", "Create or update the epic"),
    ("create_story_tasks", "Generate stories and tasks"),
    ("party_mode_refinement", "Multi-agent story refinement"),
    ("detect_commands", "AI-detect build/test/lint commands"),
    ("dev_story", "Generate implementation code"),
    ("qa_automation", "Generate QA tests"),
    ("code_review", "Architect code review loop"),
    ("commit_and_push", "Git commit and push"),
    ("create_pull_request", "Create GitHub PR"),
]


def select_skip_nodes(pre_checked: list[str] | None = None) -> list[str]:
    """Show a checkbox list of graph nodes the user can skip.

    Args:
        pre_checked: Node names to pre-select (e.g. when --story-key is used).

    Returns a list of node names to skip (empty = skip nothing).
    """
    _pre = set(pre_checked or [])
    choices = [
        questionary.Choice(
            title=f"{name} — {desc}",
            value=name,
            checked=name in _pre,
        )
        for name, desc in SKIPPABLE_NODES
    ]

    selected = questionary.checkbox(
        "Select nodes to skip (space to toggle, enter to confirm):",
        choices=choices,
    ).ask()

    return selected if selected is not None else []
