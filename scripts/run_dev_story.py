"""
Run the dev_story node in isolation with a hand-crafted story.

Usage:
    uv run python scripts/run_dev_story.py

The script calls make_dev_story_node() directly — no graph, no Jira, no GitHub.
Claude is the only external service called (unless you set DRY_RUN=true below).

Customise the STORY_* constants at the top of this file to match the feature
you want to prototype.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ── Configure here ────────────────────────────────────────────────────────────

DRY_RUN = False          # True → skip file writes and build/test/lint checks
STORY_ID = "DUMMY-42"

STORY_CONTENT = """
## Summary
Add a simple health-check endpoint to the Express API.

## Description
The service needs a `GET /health` endpoint that returns a JSON response so that
load balancers and monitoring tools can verify the service is alive.

## Implementation Notes
- Add route in `src/routes/health.ts`
- Return `{ status: "ok", timestamp: "<ISO8601>" }`
- No authentication required
- Should respond within 50ms
"""

ACCEPTANCE_CRITERIA = [
    "GET /health returns HTTP 200",
    "Response body contains { status: 'ok', timestamp: '<ISO8601>' }",
    "No authentication header required",
    "Response time is under 50ms under normal load",
]

ARCHITECT_OUTPUT = """
Use a plain Express Router. No database calls. Keep it stateless.
Place the route file at src/routes/health.ts and register it in src/app.ts.
"""

DEVELOPER_OUTPUT = """
Create src/routes/health.ts exporting a Router with a single GET handler.
Import and mount it in src/app.ts under /health.
Add a unit test in tests/routes/health.test.ts using supertest.
"""

DEV_GUIDELINES = None   # or a string with project-specific coding rules

BUILD_COMMANDS: list[str] = []   # e.g. ["npm run build"]
TEST_COMMANDS: list[str] = []    # e.g. ["npm test"]
LINT_COMMANDS: list[str] = []    # e.g. ["npm run lint"]

# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env", override=True)

    if DRY_RUN:
        os.environ["BMAD_DRY_RUN"] = "true"

    from bmad_orchestrator.config import Settings
    from bmad_orchestrator.nodes.dev_story import make_dev_story_node
    from bmad_orchestrator.services.claude_service import ClaudeService
    from bmad_orchestrator.utils.logger import configure_logging
    from bmad_orchestrator.state import OrchestratorState

    configure_logging(verbose=True)
    settings = Settings()  # type: ignore[call-arg]

    node = make_dev_story_node(ClaudeService(settings), settings)

    # Minimal state — only the fields dev_story reads
    state: OrchestratorState = {
        # Required inputs
        "team_id": "local",
        "input_prompt": STORY_CONTENT,
        "project_context": None,
        "current_epic_id": "DUMMY-1",
        "current_story_id": STORY_ID,
        "epic_routing_reason": None,
        # Story content
        "story_content": STORY_CONTENT,
        "acceptance_criteria": ACCEPTANCE_CRITERIA,
        "dependencies": None,
        "qa_scope": None,
        "definition_of_done": None,
        # Party mode outputs
        "architect_output": ARCHITECT_OUTPUT,
        "developer_output": DEVELOPER_OUTPUT,
        # Build toolchain
        "build_commands": BUILD_COMMANDS,
        "test_commands": TEST_COMMANDS,
        "lint_commands": LINT_COMMANDS,
        "dev_guidelines": DEV_GUIDELINES,
        # Git / GitHub (not used by dev_story)
        "base_branch": None,
        "branch_name": None,
        "commit_sha": None,
        "pr_url": None,
        # Review loop (not used by dev_story)
        "review_loop_count": 0,
        "code_review_issues": [],
        # Accumulated lists
        "touched_files": [],
        "qa_results": [],
        "execution_log": [],
        # Misc
        "failure_state": None,
        "retry_guidance": None,
    }

    print("\n=== Running dev_story node ===\n")
    result = node(state)

    if result.get("failure_state"):
        print("\n❌ dev_story FAILED:")
        print(result["failure_state"])
    else:
        touched = result.get("touched_files", [])
        print(f"\n✅ dev_story SUCCEEDED — {len(touched)} file(s) written:")
        for f in touched:
            print(f"   {f}")

    print("\n=== Execution log ===")
    for entry in result.get("execution_log", []):
        print(f"  [{entry['node']}] {entry['message']}")

    print("\n=== Full result keys ===")
    print(json.dumps({k: str(v)[:120] for k, v in result.items()}, indent=2))


if __name__ == "__main__":
    main()
