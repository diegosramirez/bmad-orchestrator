from __future__ import annotations

import json
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
from bmad_orchestrator.nodes.create_github_issue import make_create_github_issue_node
from bmad_orchestrator.nodes.create_or_correct_epic import make_create_or_correct_epic_node
from bmad_orchestrator.nodes.create_pull_request import make_create_pull_request_node
from bmad_orchestrator.nodes.create_story_tasks import make_create_story_tasks_node
from bmad_orchestrator.nodes.detect_commands import make_detect_commands_node
from bmad_orchestrator.nodes.dev_story import make_dev_story_node
from bmad_orchestrator.nodes.dev_story_fix_loop import make_fix_loop_node
from bmad_orchestrator.nodes.e2e_automation import make_e2e_automation_node, make_e2e_router
from bmad_orchestrator.nodes.e2e_fix_loop import make_e2e_fix_loop_node
from bmad_orchestrator.nodes.epic_architect import make_epic_architect_node
from bmad_orchestrator.nodes.party_mode_refinement import make_party_mode_node
from bmad_orchestrator.nodes.qa_automation import make_qa_automation_node
from bmad_orchestrator.nodes.update_jira_branch import make_update_jira_branch_node
from bmad_orchestrator.nodes.validate_environment import make_validate_environment_node
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
from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.utils.project_context import (
    gather_project_context,
    read_dev_guidelines,
)

logger = get_logger(__name__)

# Human-readable labels for step-level Jira notifications (node name -> label).
NODE_LABELS: dict[str, str] = {
    "check_epic_state": "Check epic state",
    "create_or_correct_epic": "Create or correct epic",
    "create_story_tasks": "Create story tasks",
    "party_mode_refinement": "Party mode refinement",
    "detect_commands": "Detect commands",
    "validate_environment": "Validate environment",
    "create_github_issue": "Create GitHub Issue",
    "dev_story": "Dev story",
    "qa_automation": "QA automation",
    "code_review": "Code review",
    "dev_story_fix_loop": "Dev story fix loop",
    "e2e_automation": "E2E automation",
    "e2e_fix_loop": "E2E fix loop",
    "fail_with_state": "Fail with state",
    "commit_and_push": "Commit and push",
    "update_jira_branch": "Update Jira branch field",
    "create_pull_request": "Create pull request",
    "epic_architect": "Epic architect",
}


def _route_after_create_or_correct_epic(settings: Settings) -> str:
    """Target after ``create_or_correct_epic``: Forge discovery ends at END (no story tasks)."""
    if settings.execution_mode == "epic_architect":
        return "epic_architect"
    if settings.execution_mode == "discovery":
        return "discovery_epic_end"
    return "create_story_tasks"


def _make_skip_node(name: str) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Return a no-op node that logs a skip entry and passes through."""

    def _skip(state: OrchestratorState) -> dict[str, Any]:
        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": name,
            "message": "Skipped (--skip-nodes)",
            "dry_run": False,
        }
        return {"execution_log": [log_entry], "_skipped": True}

    return _skip


def _step_status_suffix(node_name: str, settings: Settings | None = None) -> str:
    """Return trailing status (Process continuing / completed / finished)."""
    if node_name in ("create_pull_request", "epic_architect"):
        return "🎉 Process completed successfully"
    if node_name == "fail_with_state":
        return "Process finished."
    if (
        settings is not None
        and settings.execution_mode == "discovery"
        and node_name == "create_or_correct_epic"
    ):
        return "🎉 Process completed successfully"
    return "⏩ Process continuing..."


def _format_step_completed_line(label: str, *, skipped: bool = False) -> str:
    """Return a 'Step completed' line with a UTC timestamp in '[DD Mon YYYY - HH:MM]' format."""
    ts = datetime.now(UTC).strftime("%d %b %Y - %H:%M")
    if skipped:
        return f"[{ts}] ⏭️ Step skipped: {label}"
    return f"[{ts}] ✅ Step completed: {label}"


def _execution_log_indicates_skip(out: dict[str, Any]) -> bool:
    """True when the node's output is only a ``--skip-nodes`` skip (omit Step completed in Jira)."""
    for entry in out.get("execution_log") or []:
        if isinstance(entry, dict) and "Skipped (--skip-nodes)" in (entry.get("message") or ""):
            return True
    return False


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
    """Wrap a node with Jira step notifications (step lines + status; supports skip)."""

    def _wrapped(state: OrchestratorState) -> dict[str, Any]:
        notify_key = state.get("notify_jira_story_key")
        comment_id = state.get("step_notification_comment_id")
        current_body = state.get("step_notification_comment_body") or ""
        label = NODE_LABELS.get(node_name, node_name.replace("_", " ").title())
        status = _step_status_suffix(node_name, settings)

        if not notify_key or settings.dry_run:
            return node_fn(state)

        if comment_id is None:
            # First step: create comment with "Process started"
            body_init = "🚀 Process started"
            try:
                new_comment_id = jira.add_comment(
                    notify_key, body_init,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "step_notification_failed",
                    story_key=notify_key,
                )
                return node_fn(state)
            if new_comment_id is None:
                return node_fn(state)
            out = node_fn(state)
            skipped = _execution_log_indicates_skip(out) or bool(out.get("_skipped"))
            step_line = _format_step_completed_line(label, skipped=skipped)
            body = body_init + "\n\n" + step_line + "\n\n" + status
            try:
                jira.update_comment(notify_key, new_comment_id, body)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "step_notification_failed",
                    story_key=notify_key,
                )
            return {
                **out,
                "step_notification_comment_id": new_comment_id,
                "step_notification_comment_body": body,
            }

        # Later steps: strip previous status, append step + new status
        out = node_fn(state)
        skipped = _execution_log_indicates_skip(out) or bool(out.get("_skipped"))
        base = _strip_trailing_status(current_body)
        step_line = _format_step_completed_line(label, skipped=skipped)
        body = base + "\n" + step_line + "\n\n" + status
        try:
            jira.update_comment(notify_key, comment_id, body)
        except Exception:  # noqa: BLE001
            logger.warning(
                "step_notification_failed",
                story_key=notify_key,
            )
        return {**out, "step_notification_comment_body": body}

    return _wrapped


def _wrap_with_slack_notifications(
    slack: SlackServiceProtocol,
    settings: Settings,
    node_name: str,
    node_fn: Callable[[OrchestratorState], dict[str, Any]],
    thread_ts_holder: list[str | None],
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Wrap a node to post Slack messages in a per-run thread.

    The first node creates a root message (run header) and stores its ``ts``
    in state as ``slack_thread_ts``.  Subsequent nodes post replies to that
    thread.  *thread_ts_holder* is a mutable single-element list shared across
    all wrapped nodes so the verbose event callback can read the current ts.
    """

    def _wrapped(state: OrchestratorState) -> dict[str, Any]:
        thread_ts = state.get("slack_thread_ts") or None
        # Keep the shared holder in sync for the verbose callback
        if thread_ts and thread_ts_holder[0] is None:
            thread_ts_holder[0] = thread_ts

        label = NODE_LABELS.get(node_name, node_name.replace("_", " ").title())
        team_id = state.get("team_id", "")
        story_id = state.get("current_story_id") or state.get("input_prompt", "")

        try:
            out = node_fn(state)
        except Exception as exc:
            # Node crashed — post failure to Slack, then re-raise
            error_text = f":x: *{label}* — crashed\n>{str(exc)[:200]}"
            try:
                if thread_ts is None:
                    header = f":rocket: *BMAD Run* — [{team_id}] {story_id}"
                    slack.post_message(f"{header}\n{error_text}")
                else:
                    slack.post_thread_reply(thread_ts, error_text)
            except Exception:  # noqa: BLE001
                logger.warning("slack_crash_notification_failed", node=node_name)
            raise

        failure = out.get("failure_state") or out.get("failure_diagnostic")
        pr_url = out.get("pr_url")
        blocks: list[dict[str, Any]] | None = None

        if failure:
            text = f":x: *{label}* — pipeline failed\n>{str(failure)[:200]}"
            # Retry button only makes sense when a branch exists (code was committed)
            branch = out.get("branch_name") or state.get("branch_name") or ""
            if branch:
                retry_meta = json.dumps(
                    {
                        "branch": branch,
                        "team_id": team_id,
                        "target_repo": settings.github_repo or "",
                        "story_key": state.get("current_story_id") or "",
                        "thread_ts": thread_ts or "",
                    }
                )
                blocks = [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": text},
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Retry"},
                                "style": "primary",
                                "action_id": "bmad_retry",
                                "value": retry_meta,
                            }
                        ],
                    },
                ]
        elif pr_url:
            text = f":tada: *PR created:* {pr_url}"
            branch = out.get("branch_name") or state.get("branch_name") or ""
            if branch:
                refine_meta = json.dumps(
                    {
                        "branch": branch,
                        "team_id": team_id,
                        "target_repo": settings.github_repo or "",
                        "story_key": state.get("current_story_id") or "",
                        "thread_ts": thread_ts or "",
                    }
                )
                blocks = [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": text},
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Refine"},
                                "action_id": "bmad_refine",
                                "value": refine_meta,
                            }
                        ],
                    },
                ]
        elif out.get("_skipped"):
            text = f":fast_forward: *{label}* skipped"
        else:
            text = f":white_check_mark: *{label}* completed"

        if thread_ts is None:
            # First step — create root message (run header), store ts
            header = f":rocket: *BMAD Run* — [{team_id}] {story_id}"
            ts = slack.post_message(f"{header}\n{text}", blocks=blocks)
            if ts:
                thread_ts_holder[0] = ts
                return {**out, "slack_thread_ts": ts}
        else:
            slack.post_thread_reply(thread_ts, text, blocks=blocks)

        return out

    return _wrapped


def _make_verbose_callback(
    slack: SlackServiceProtocol,
    settings: Settings,
    thread_ts_holder: list[str | None],
) -> Callable[[str], None]:
    """Create the on_event callback for verbose Slack mode.

    Returns a no-op if verbose mode is disabled.  Otherwise returns a function
    that posts each message as a thread reply, silently swallowing errors so
    that a Slack hiccup never crashes the pipeline.
    """
    if not settings.slack_verbose or not settings.slack_notify:
        return lambda _msg: None

    def _post(msg: str) -> None:
        ts = thread_ts_holder[0]
        if ts:
            try:
                slack.post_thread_reply(ts, msg)
            except Exception:  # noqa: BLE001
                pass  # never crash the pipeline for a Slack failure

    return _post


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
    git_settings = settings.model_copy(update={"dry_run": True}) if settings.jira_only else settings
    git = GitService(git_settings)
    github = create_github_service(git_settings)
    slack = create_slack_service(settings)

    # ── Verbose Slack callback (shared mutable holder for thread_ts) ────────
    thread_ts_holder: list[str | None] = [None]
    on_event = _make_verbose_callback(slack, settings, thread_ts_holder)

    # ── BMAD workflow runner (loads real workflow files for epic/story creation) ─
    bmad_runner = BmadWorkflowRunner(claude, settings)

    # ── Build node callables via factories ────────────────────────────────────
    builder: StateGraph = StateGraph(OrchestratorState)
    skip = set(settings.skip_nodes)

    def _node(name: str, factory_fn: Callable[..., Any]) -> None:
        """Register a real node or a no-op skip node, wrapped with notifications."""
        raw = _make_skip_node(name) if name in skip else factory_fn
        wrapped = _wrap_with_step_notifications(jira, settings, name, raw)
        wrapped = _wrap_with_slack_notifications(
            slack,
            settings,
            name,
            wrapped,
            thread_ts_holder,
        )
        builder.add_node(name, wrapped)

    _node(
        "check_epic_state",
        make_check_epic_state_node(jira, claude, settings, on_event=on_event),
    )
    _node(
        "create_or_correct_epic",
        make_create_or_correct_epic_node(jira, claude, settings, bmad_runner, on_event=on_event),
    )
    _node(
        "epic_architect",
        make_epic_architect_node(claude, jira, settings, on_event=on_event),
    )
    _node(
        "create_story_tasks",
        make_create_story_tasks_node(jira, claude, settings, bmad_runner, on_event=on_event),
    )
    _node("party_mode_refinement", make_party_mode_node(claude, jira, settings, on_event=on_event))
    _node("detect_commands", make_detect_commands_node(claude, settings, on_event=on_event))
    _node("validate_environment", make_validate_environment_node(settings, on_event=on_event))
    _node(
        "create_github_issue",
        make_create_github_issue_node(github, jira, settings),
    )
    _node("dev_story", make_dev_story_node(claude_agent, settings, on_event=on_event))
    _node("qa_automation", make_qa_automation_node(claude_agent, settings, on_event=on_event))
    _node("code_review", make_code_review_node(claude_agent, settings, on_event=on_event))
    _node("dev_story_fix_loop", make_fix_loop_node(claude_agent, settings, on_event=on_event))
    _node("e2e_automation", make_e2e_automation_node(claude_agent, settings, on_event=on_event))
    _node("e2e_fix_loop", make_e2e_fix_loop_node(claude_agent, settings, on_event=on_event))
    _node("fail_with_state", make_fail_with_state_node(settings))
    _node("commit_and_push", make_commit_and_push_node(git, settings))
    _node("update_jira_branch", make_update_jira_branch_node(jira, settings))
    _node("create_pull_request", make_create_pull_request_node(github, settings))

    # ── Linear edges ──────────────────────────────────────────────────────────
    builder.add_edge(START, "check_epic_state")
    builder.add_edge("check_epic_state", "create_or_correct_epic")

    def _after_create_epic_router(_state: OrchestratorState) -> str:
        return _route_after_create_or_correct_epic(settings)

    builder.add_conditional_edges(
        "create_or_correct_epic",
        _after_create_epic_router,
        {
            "epic_architect": "epic_architect",
            "discovery_epic_end": END,
            "create_story_tasks": "create_story_tasks",
        },
    )
    builder.add_edge("epic_architect", END)
    builder.add_edge("create_story_tasks", "party_mode_refinement")

    def _after_party_mode_router(_state: OrchestratorState) -> str:
        if settings.execution_mode == "stories_breakdown":
            return "stories_breakdown_end"
        return "detect_commands"

    builder.add_conditional_edges(
        "party_mode_refinement",
        _after_party_mode_router,
        {
            "stories_breakdown_end": END,
            "detect_commands": "detect_commands",
        },
    )

    # ── Execution mode routing: inline | github-agent | discovery ───────────
    def _execution_mode_router(_state: OrchestratorState) -> str:
        if settings.execution_mode == "github-agent":
            return "create_github_issue"
        if settings.execution_mode == "discovery":
            return "discovery_end"
        return "validate_environment"

    builder.add_conditional_edges(
        "detect_commands",
        _execution_mode_router,
        {
            "validate_environment": "validate_environment",
            "create_github_issue": "create_github_issue",
            "discovery_end": END,
        },
    )
    builder.add_edge("create_github_issue", END)

    def _after_validate_env(state: OrchestratorState) -> str:
        if state.get("failure_state"):
            return "fail_with_state"
        return "dev_story"

    builder.add_conditional_edges(
        "validate_environment",
        _after_validate_env,
        {
            "dev_story": "dev_story",
            "fail_with_state": "fail_with_state",
        },
    )

    builder.add_edge("dev_story", "qa_automation")
    builder.add_edge("qa_automation", "code_review")

    # ── Conditional edge: code review → fix loop OR E2E ─────────────────────
    builder.add_conditional_edges(
        "code_review",
        make_review_router(settings),
        {
            "dev_story_fix_loop": "dev_story_fix_loop",
            "e2e_automation": "e2e_automation",
            "fail_with_state": "fail_with_state",
        },
    )
    builder.add_edge("fail_with_state", "commit_and_push")
    # Back-edge: fix loop → code review (developer self-verifies inside the node)
    builder.add_edge("dev_story_fix_loop", "code_review")

    # ── E2E automation → fix loop or commit ───────────────────────────────────
    builder.add_conditional_edges(
        "e2e_automation",
        make_e2e_router(settings),
        {
            "commit_and_push": "commit_and_push",
            "e2e_fix_loop": "e2e_fix_loop",
        },
    )
    builder.add_edge("e2e_fix_loop", "e2e_automation")

    # ── Terminal edges ────────────────────────────────────────────────────────
    builder.add_edge("commit_and_push", "update_jira_branch")
    builder.add_edge("update_jira_branch", "create_pull_request")
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
    guidance: str | None = None,
    slack_thread_ts: str | None = None,
) -> OrchestratorState:
    """Return a fully-initialised empty state for a new run."""
    cwd = Path.cwd()
    return OrchestratorState(
        team_id=team_id,
        input_prompt=input_prompt,
        project_context=gather_project_context(cwd) or None,
        current_epic_id=epic_key,
        current_story_id=story_key,
        created_story_ids=None,
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
        github_issue_url=None,
        github_issue_number=None,
        auto_execute_issue=False,
        code_agent="",
        review_loop_count=0,
        code_review_issues=[],
        touched_files=[],
        qa_results=[],
        execution_log=[],
        failure_state=None,
        failure_diagnostic=None,
        slack_thread_ts=slack_thread_ts or None,
        tests_passing=None,
        test_failure_output=None,
        retry_guidance=guidance,
        setup_commands=[],
        build_commands=[],
        test_commands=[],
        lint_commands=[],
        e2e_commands=[],
        dev_guidelines=read_dev_guidelines(cwd) or None,
        total_cost_usd=0.0,
        e2e_results=[],
        e2e_tests_passing=None,
        e2e_failure_output=None,
        e2e_loop_count=0,
    )
