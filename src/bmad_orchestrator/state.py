from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


class CodeReviewIssue(TypedDict):
    severity: str  # "low" | "medium" | "high" | "critical"
    file: str
    line: int | None
    description: str
    fix_required: bool


class QAResult(TypedDict):
    test_file: str
    passed: bool
    output: str


class ExecutionLogEntry(TypedDict):
    timestamp: str
    node: str
    message: str
    dry_run: bool


class FileOperation(TypedDict):
    action: str  # "create" | "modify" | "delete"
    path: str
    content: str


class OrchestratorState(TypedDict):
    # ── Inputs (set once at start) ────────────────────────────────────────────
    team_id: str
    input_prompt: str
    project_context: str | None

    # ── Jira artifacts ────────────────────────────────────────────────────────
    current_epic_id: str | None
    current_story_id: str | None
    # When set, step start/finish notifications are posted as comments on this story (e.g. webhook runs).
    notify_jira_story_key: str | None
    # Single comment id and body for step notifications (create once, then update/append).
    step_notification_comment_id: str | None
    step_notification_comment_body: str | None

    # ── Epic decision / mutation tracking ──────────────────────────────────────
    # Reason for the most recent epic routing decision (add_to_existing vs create_new)
    epic_routing_reason: str | None

    # ── Story content ─────────────────────────────────────────────────────────
    story_content: str | None
    acceptance_criteria: list[str] | None
    dependencies: list[str] | None
    qa_scope: list[str] | None
    definition_of_done: list[str] | None

    # ── Party mode outputs ────────────────────────────────────────────────────
    architect_output: str | None
    developer_output: str | None

    # ── Git / GitHub artifacts ────────────────────────────────────────────────
    base_branch: str | None
    branch_name: str | None
    commit_sha: str | None
    pr_url: str | None

    # ── Review loop ───────────────────────────────────────────────────────────
    review_loop_count: int
    code_review_issues: list[CodeReviewIssue]

    # ── QA ────────────────────────────────────────────────────────────────────
    qa_results: Annotated[list[QAResult], operator.add]

    # ── Files written to disk (accumulated across all generator nodes) ────────
    touched_files: Annotated[list[str], operator.add]

    # ── Execution tracking ────────────────────────────────────────────────────
    execution_log: Annotated[list[ExecutionLogEntry], operator.add]
    failure_state: str | None

    # ── Failure diagnostic (architect analysis when review loops exhaust) ─────
    failure_diagnostic: str | None

    # ── Slack threading ──────────────────────────────────────────────────────
    slack_thread_ts: str | None

    # ── User guidance (injected on --retry / --resume --guidance "...") ───────
    retry_guidance: str | None

    # ── Test gate ───────────────────────────────────────────────────────────────
    tests_passing: bool | None  # None = not yet tested, True/False after validation
    test_failure_output: str | None  # Error text from independent test run

    # ── Build/test/lint commands (detected from project config at start) ──────
    build_commands: list[str]
    test_commands: list[str]
    lint_commands: list[str]
    dev_guidelines: str | None
