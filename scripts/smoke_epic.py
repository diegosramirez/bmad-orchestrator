"""
Minimal smoke test: find or create a BMAD Epic in Jira.

This script exercises ONLY the Jira integration — no Claude, no Git, no graph.
It's the fastest way to verify your credentials and Jira connectivity before
running the full orchestrator.

Usage:
    cd apps/ai-workflow
    uv run python scripts/smoke_epic.py [--team-id pug] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the repo root or from apps/ai-workflow/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

from bmad_orchestrator.config import Settings  # noqa: E402
from bmad_orchestrator.services.jira_service import JiraService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="BMAD Epic smoke test")
    parser.add_argument(
        "--team-id",
        default=None,
        help="Team ID label used in Jira (defaults to BMAD_JIRA_PROJECT_KEY lowercased)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without making any Jira changes",
    )
    args = parser.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    if args.dry_run:
        settings = settings.model_copy(update={"dry_run": True})

    team_id = args.team_id or settings.jira_project_key.lower()

    print(f"Project : {settings.jira_project_key}")
    print(f"Jira URL: {settings.jira_base_url}")
    print(f"Team ID : {team_id}")
    print(f"Dry run : {settings.dry_run}")
    print()

    jira = JiraService(settings)

    # ── Step 1: search for existing epics ────────────────────────────────────
    print(f"Searching for open epics in project {settings.jira_project_key}...")
    epics = jira.find_epic_by_team(team_id)

    if epics:
        print(f"  ✓ Found {len(epics)} epic(s):")
        for e in epics:
            print(f"    - {e['key']}: {e['summary']} ({e['status']})")
        return

    # ── Step 2: create a new epic ─────────────────────────────────────────────
    print("  No open epics found.")
    if settings.dry_run:
        print("  [DRY RUN] Would create epic — skipping (dry_run=True)")
        print("  Fake epic key: DRY-001")
        return

    print("  Creating smoke-test epic...")
    epic = jira.create_epic(
        summary="[BMAD Smoke Test] Orchestrator validation epic",
        description=(
            "Auto-created by the BMAD orchestrator smoke test.\n"
            "This epic validates that the Jira integration is working correctly.\n"
            "Safe to delete."
        ),
        team_id=team_id,
    )
    print(f"  ✓ Created: {epic['key']} — {epic['summary']}")
    print()
    print("Next step: run the full dry-run to test the graph structure:")
    print(f"  uv run bmad-orchestrator --team-id {team_id} --prompt 'Test feature' --dry-run")


if __name__ == "__main__":
    main()
