#!/usr/bin/env python3
"""Clean up dummy Jira data (epics, stories, tasks + counter).

Usage:
    uv run python scripts/clean_dummy_jira.py            # preview (dry-run)
    uv run python scripts/clean_dummy_jira.py --confirm  # actually delete

Respects BMAD_DUMMY_DATA_DIR env var (default: ~/.bmad/dummy).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SUBDIRS = ("epics", "stories", "tasks")


def main() -> None:
    confirm = "--confirm" in sys.argv

    base_dir = Path(os.environ.get("BMAD_DUMMY_DATA_DIR", "~/.bmad/dummy")).expanduser()
    jira_dir = base_dir / "jira"

    if not jira_dir.exists():
        print(f"Nothing to clean — {jira_dir} does not exist.")
        return

    to_delete: list[Path] = []

    for subdir in SUBDIRS:
        for md_file in sorted((jira_dir / subdir).glob("*.md")):
            to_delete.append(md_file)

    counter = jira_dir / "_counter.json"
    if counter.exists():
        to_delete.append(counter)

    if not to_delete:
        print("Nothing to clean — no dummy Jira files found.")
        return

    counts = {s: 0 for s in SUBDIRS}
    for p in to_delete:
        if p.parent.name in counts:
            counts[p.parent.name] += 1

    print(f"Dummy Jira data in: {jira_dir}")
    print(f"  Epics   : {counts['epics']}")
    print(f"  Stories : {counts['stories']}")
    print(f"  Tasks   : {counts['tasks']}")
    print(f"  Counter : {'yes' if counter.exists() else 'no'}")
    print()

    if not confirm:
        print("Dry-run — pass --confirm to actually delete.")
        return

    for p in to_delete:
        p.unlink()
        print(f"  deleted {p.relative_to(base_dir)}")

    print(f"\nDone — {len(to_delete)} file(s) removed.")


if __name__ == "__main__":
    main()
