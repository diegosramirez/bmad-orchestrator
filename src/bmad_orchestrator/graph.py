from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from rich.console import Console

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.check_epic_state import make_check_epic_state_node
from bmad_orchestrator.nodes.code_review import (
    make_code_review_node,
    make_fail_with_state_node,
    make_review_router,
)
from bmad_orchestrator.nodes.commit_and_push import make_commit_and_push_node
from bmad_orchestrator.nodes.create_or_correct_epic import make_create_or_correct_epic_node
from bmad_orchestrator.nodes.create_pull_request import make_create_pull_request_node
from bmad_orchestrator.nodes.create_story_tasks import make_create_story_tasks_node
from bmad_orchestrator.nodes.detect_commands import make_detect_commands_node
from bmad_orchestrator.nodes.dev_story import make_dev_story_node
from bmad_orchestrator.nodes.dev_story_fix_loop import make_fix_loop_node
from bmad_orchestrator.nodes.party_mode_refinement import make_party_mode_node
from bmad_orchestrator.nodes.qa_automation import make_qa_automation_node
from bmad_orchestrator.services.bmad_workflow_runner import BmadWorkflowRunner
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.services.git_service import GitService
from bmad_orchestrator.services.protocols import SlackServiceProtocol
from bmad_orchestrator.services.service_factory import (
    create_github_service,
    create_jira_service,
    create_slack_service,
)
from bmad_orchestrator.state import ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.project_context import (
    gather_project_context,
    read_dev_guidelines,
)

# Human-readable labels for step-level Jira notifications (node name -> label).
NODE_LABELS: dict[str, str] = {
    "check_epic_state": "Check epic state",
    "create_or_correct_epic": "Create or correct epic",
    "create_story_tasks": "Create story tasks",
    "party_mode_refinement": "Party mode refinement",
    "detect_commands": "Detect commands",
    "dev_story": "Dev story",
    "qa_automation": "QA automation",
    "code_review": "Code review",
    "dev_story_fix_loop": "Dev story fix loop",
    "fail_with_state": "Fail with state",
    "commit_and_push": "Commit and push",
    "create_pull_request": "Create pull request",
}


def _make_skip_node(name: str) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Return a no-op node that logs a skip entry and passes through."""

    def _skip(state: OrchestratorState) -> dict[str, Any]:
        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": name,
            "message": "Skipped (--skip-nodes)",
            "dry_run": False,
        }
        return {"execution_log": [log_entry]}

    return _skip


def _step_status_suffix(node_name: str) -> str:
    """Return the status line to show once at the end (Process continuing / completed / finished)."""
    if node_name == "create_pull_request":
        return "🎉 Process completed successfully"
    if node_name == "fail_with_state":
        return "Process finished."
    return "⏩ Process continuing..."


def _format_step_completed_line(label: str) -> str:
    """Return a 'Step completed' line with a UTC timestamp in '[DD Mon YYYY - HH:MM]' format."""
    ts = datetime.now(UTC).strftime("%d %b %Y - %H:%M")
    return f"[{ts}] ✅ Step completed: {label}"


def _strip_trailing_status(body: str) -> str:
    """Remove the trailing status line so we can append a new step then a new status."""
    for status in (
        "⏩ Process continuing...",
        "⏭️ Process continuing...",
        "🎉 Process completed successfully",
        "Process finished.",
    ):
        if body.endswith("\n\n" + status):
            return body[: -len("\n\n" + status)].rstrip()
        if body.endswith("\n" + status):
            return body[: -len("\n" + status)].rstrip()
    return body


def _wrap_with_step_notifications(
    jira: Any,
    settings: Settings,
    node_name: str,
    node_fn: Callable[[OrchestratorState], dict[str, Any]],
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Wrap a node: one Jira comment; list of Step completed lines, single status line at the end."""

    def _wrapped(state: OrchestratorState) -> dict[str, Any]:
        notify_key = state.get("notify_jira_story_key")
        comment_id = state.get("step_notification_comment_id")
        current_body = state.get("step_notification_comment_body") or ""
        label = NODE_LABELS.get(node_name, node_name.replace("_", " ").title())
        status = _step_status_suffix(node_name)

        if not notify_key or settings.dry_run:
            return node_fn(state)

        if comment_id is None:
            # First step: create comment with "Process started"
            body_init = "🚀 Process started"
            new_comment_id = jira.add_comment(notify_key, body_init)
            if new_comment_id is None:
                return node_fn(state)
            out = node_fn(state)
            # List of steps, then one status line at the end
            step_line = _format_step_completed_line(label)
            body = body_init + "\n\n" + step_line + "\n\n" + status
            jira.update_comment(notify_key, new_comment_id, body)
            return {
                **out,
                "step_notification_comment_id": new_comment_id,
                "step_notification_comment_body": body,
            }

        # Later steps: strip previous status, append step (single newline between steps) and new status
        out = node_fn(state)
        base = _strip_trailing_status(current_body)
        step_line = _format_step_completed_line(label)
        body = base + "\n" + step_line + "\n\n" + status
        jira.update_comment(notify_key, comment_id, body)
        return {**out, "step_notification_comment_body": body}

    return _wrapped


def _wrap_with_slack_notifications(
    slack: SlackServiceProtocol,
    settings: Settings,
    node_name: str,
    node_fn: Callable[[OrchestratorState], dict[str, Any]],
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Wrap a node to post Slack messages in a per-run thread.

    The first node creates a root message (run header) and stores its ``ts``
    in state as ``slack_thread_ts``.  Subsequent nodes post replies to that
    thread.
    """

    def _wrapped(state: OrchestratorState) -> dict[str, Any]:
        thread_ts = state.get("slack_thread_ts")
        out = node_fn(state)

        label = NODE_LABELS.get(node_name, node_name.replace("_", " ").title())
        team_id = state.get("team_id", "")
        story_id = state.get("current_story_id") or state.get("input_prompt", "")

        failure = out.get("failure_state") or out.get("failure_diagnostic")
        pr_url = out.get("pr_url")

        if failure:
            text = f":x: *{label}* — pipeline failed\n>{str(failure)[:200]}"
        elif pr_url:
            text = f":tada: *PR created:* {pr_url}"
        else:
            text = f":white_check_mark: *{label}* completed"

        if thread_ts is None:
            # First step — create root message (run header), store ts
            header = f":rocket: *BMAD Run* — [{team_id}] {story_id}"
            ts = slack.post_message(f"{header}\n{text}")
            if ts:
                return {**out, "slack_thread_ts": ts}
        else:
            slack.post_thread_reply(thread_ts, text)

        return out

    return _wrapped


def build_graph(
    settings: Settings,
    *,
    console: Console | None = None,
) -> tuple[Any, SqliteSaver, ClaudeService]:
    """
    Assemble the full BMAD orchestration StateGraph.

    Returns:
        (compiled_graph, checkpointer) — the checkpointer is returned so the
        CLI can call `checkpointer.get()` for the `--resume` flag.
    """
    # ── Instantiate services via factory (composition root) ─────────────────
    jira = create_jira_service(settings)
    claude = ClaudeService(settings, console=console)
    claude_agent = ClaudeAgentService(settings, usage_tracker=claude._usage)

    # When jira_only, force Git/GitHub into dry-run regardless of global flag
    git_settings = (
        settings.model_copy(update={"dry_run": True}) if settings.jira_only else settings
    )
    git = GitService(git_settings)
    github = create_github_service(git_settings)
    slack = create_slack_service(settings)

    # ── BMAD workflow runner (loads real workflow files for epic/story creation) ─
    bmad_runner = BmadWorkflowRunner(claude, settings)

    # ── Build node callables via factories ────────────────────────────────────
    builder: StateGraph = StateGraph(OrchestratorState)
    skip = set(settings.skip_nodes)

    def _node(name: str, factory_fn: Callable[..., Any]) -> None:
        """Register a real node or a no-op skip node, wrapped with notifications."""
        raw = _make_skip_node(name) if name in skip else factory_fn
        wrapped = _wrap_with_step_notifications(jira, settings, name, raw)
        wrapped = _wrap_with_slack_notifications(slack, settings, name, wrapped)
        builder.add_node(name, wrapped)

    _node("check_epic_state", make_check_epic_state_node(jira, claude, settings))
    _node(
        "create_or_correct_epic",
        make_create_or_correct_epic_node(jira, claude, settings, bmad_runner),
    )
    _node(
        "create_story_tasks",
        make_create_story_tasks_node(jira, claude, settings, bmad_runner),
    )
    _node("party_mode_refinement", make_party_mode_node(claude, jira, settings))
    _node("detect_commands", make_detect_commands_node(claude, settings))
    _node("dev_story", make_dev_story_node(claude_agent, settings))
    _node("qa_automation", make_qa_automation_node(claude_agent, settings))
    _node("code_review", make_code_review_node(claude_agent, settings))
    _node("dev_story_fix_loop", make_fix_loop_node(claude_agent, settings))
    _node("fail_with_state", make_fail_with_state_node(settings))
    _node("commit_and_push", make_commit_and_push_node(git, settings))
    _node("create_pull_request", make_create_pull_request_node(github, settings))

    # ── Linear edges ──────────────────────────────────────────────────────────
    builder.add_edge(START, "check_epic_state")
    builder.add_edge("check_epic_state", "create_or_correct_epic")
    builder.add_edge("create_or_correct_epic", "create_story_tasks")
    builder.add_edge("create_story_tasks", "party_mode_refinement")
    builder.add_edge("party_mode_refinement", "detect_commands")
    builder.add_edge("detect_commands", "dev_story")
    builder.add_edge("dev_story", "qa_automation")
    builder.add_edge("qa_automation", "code_review")

    # ── Conditional edge: code review → fix loop OR commit ────────────────────
    builder.add_conditional_edges(
        "code_review",
        make_review_router(settings),
        {
            "dev_story_fix_loop": "dev_story_fix_loop",
            "commit_and_push": "commit_and_push",
            "fail_with_state": "fail_with_state",
        },
    )
    builder.add_edge("fail_with_state", "commit_and_push")
    # Back-edge: fix loop → code review (developer self-verifies inside the node)
    builder.add_edge("dev_story_fix_loop", "code_review")

    # ── Terminal edges ────────────────────────────────────────────────────────
    builder.add_edge("commit_and_push", "create_pull_request")
    builder.add_edge("create_pull_request", END)

    # ── Checkpointer ─────────────────────────────────────────────────────────
    db_path = Path(settings.checkpoint_db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    compiled = builder.compile(checkpointer=checkpointer)
    return compiled, checkpointer, claude


def make_initial_state(
    team_id: str,
    input_prompt: str,
    *,
    epic_key: str | None = None,
    story_key: str | None = None,
    story_content: str | None = None,
    acceptance_criteria: list[str] | None = None,
) -> OrchestratorState:
    """Return a fully-initialised empty state for a new run."""
    cwd = Path.cwd()
    return OrchestratorState(
        team_id=team_id,
        input_prompt=input_prompt,
        project_context=gather_project_context(cwd) or None,
        current_epic_id=epic_key,
        current_story_id=story_key,
        notify_jira_story_key=story_key,
        step_notification_comment_id=None,
        step_notification_comment_body=None,
        epic_routing_reason=None,
        story_content=story_content,
        acceptance_criteria=acceptance_criteria,
        dependencies=None,
        qa_scope=None,
        definition_of_done=None,
        architect_output=None,
        developer_output=None,
        base_branch=None,
        branch_name=None,
        commit_sha=None,
        pr_url=None,
        review_loop_count=0,
        code_review_issues=[],
        touched_files=[],
        qa_results=[],
        execution_log=[],
        failure_state=None,
        failure_diagnostic=None,
        slack_thread_ts=None,
        tests_passing=None,
        test_failure_output=None,
        retry_guidance=None,
        build_commands=[],
        test_commands=[],
        lint_commands=[],
        dev_guidelines=read_dev_guidelines(cwd) or None,
    )
