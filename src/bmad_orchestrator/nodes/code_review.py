from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_validator

from bmad_orchestrator.config import Settings
from bmad_orchestrator.nodes.dev_story import _resolve_cwd
from bmad_orchestrator.personas.loader import build_system_prompt
from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService
from bmad_orchestrator.state import CodeReviewIssue, ExecutionLogEntry, OrchestratorState
from bmad_orchestrator.utils.cost_tracking import accumulate_cost
from bmad_orchestrator.utils.json_repair import parse_stringified_list
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "code_review"

_MEDIUM_OR_ABOVE = {"medium", "high", "critical"}
_HIGH_OR_ABOVE = {"high", "critical"}
_CRITICAL_ONLY = {"critical"}

# Progressive leniency: each loop raises the bar for what blocks progress.
# This prevents the architect from endlessly finding new medium issues.
_BLOCKING_THRESHOLDS: list[set[str]] = [
    _MEDIUM_OR_ABOVE,  # loop 0 (first review): medium+ blocks
    _HIGH_OR_ABOVE,    # loop 1: only high+ blocks
    _CRITICAL_ONLY,    # loop 2+: only critical blocks
]


_MAX_ISSUES = 10  # cap issues to keep the fix loop prompt focused
_MAX_ISSUE_DESC = 200  # truncate verbose descriptions


class ReviewIssueItem(BaseModel):
    severity: str
    file: str
    line: int = 0
    description: str
    fix_required: bool = True


class ReviewResult(BaseModel):
    issues: list[ReviewIssueItem]
    overall_assessment: str

    @field_validator("issues", mode="before")
    @classmethod
    def _parse_stringified_json(cls, v: Any) -> Any:
        """Handle Claude returning issues as a JSON string."""
        return parse_stringified_list(v)


def make_code_review_node(
    agent: ClaudeAgentService,
    settings: Settings,
    *,
    on_event: Callable[[str], None] | None = None,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("architect", settings.bmad_install_dir)

    def code_review(state: OrchestratorState) -> dict[str, Any]:
        story_content = state["story_content"] or ""
        acceptance_criteria = state["acceptance_criteria"] or []
        now = datetime.now(UTC).isoformat()
        cwd_path = str(_resolve_cwd(settings, state))

        project_context = state.get("project_context") or ""
        ctx_block = (
            f"Target project context:\n{project_context}\n\n" if project_context else ""
        )

        touched_files = state.get("touched_files") or []
        files_list = "\n".join(f"- {f}" for f in dict.fromkeys(touched_files))

        loop_count = state.get("review_loop_count", 0)
        is_followup = loop_count > 0

        threshold = _blocking_threshold(loop_count)
        threshold_label = ", ".join(sorted(threshold))

        followup_block = ""
        if is_followup:
            followup_block = (
                f"This is review pass #{loop_count + 1}. The developer has "
                f"already attempted fixes. Only {threshold_label} issues will "
                f"block this code from merging.\n\n"
                f"IMPORTANT constraints for follow-up reviews:\n"
                f"- Only report issues that STILL EXIST in the current code.\n"
                f"- Do NOT invent new issues that were not in the previous "
                f"review unless they are {threshold_label}.\n"
                f"- Do NOT re-report issues that have been fixed.\n"
                f"- The code does not need to be perfect — it needs to be "
                f"correct, secure, and functional.\n\n"
            )

        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria)
        prompt = (
            f"{ctx_block}"
            f"IMPORTANT — Working directory and project context:\n"
            f"- Your CWD is: {cwd_path}\n"
            f"- Use RELATIVE paths (e.g. src/app/foo.ts) for all Read calls.\n"
            f"- Read ONLY the listed files — do not explore the project.\n\n"
            f"Review the code in the following files. Read each file before "
            f"reviewing — use the Read tool to access them:\n{files_list}\n\n"
            f"{followup_block}"
            f"RULES:\n"
            f"1. Report at most 10 issues total, prioritised by severity.\n"
            f"2. Each issue description must be 1-2 sentences max — state "
            f"WHAT is wrong and HOW to fix it. No analysis or speculation.\n"
            f"3. Only flag real, concrete issues found in the code — not "
            f"hypothetical concerns, style preferences, or edge cases "
            f"that require unusual user behavior.\n"
            f"4. Do not flag pre-existing project configuration issues "
            f"(test framework, build config, package.json) unless the "
            f"generated code directly conflicts with them.\n"
            f"5. Do not flag the same logical issue in multiple files — "
            f"report it once under the most relevant file.\n\n"
            f"Story context:\n{story_content}\n\n"
            f"Acceptance Criteria:\n{ac_text}\n\n"
            f"Severity calibration (use strictly):\n"
            f"- critical: build-breaking errors, runtime crashes, "
            f"security holes, data loss\n"
            f"- high: functional bugs visible to users, missing required "
            f"acceptance-criteria logic\n"
            f"- medium: correctness issues (wrong error handling, "
            f"race conditions, resource leaks)\n"
            f"- low: style, naming, minor optimisations, accessibility "
            f"refinements, unused code, test preferences\n\n"
            f"ALWAYS LOW (never medium+): aria attributes, CSS naming, "
            f"unused getters, empty lifecycle hooks, test framework "
            f"choice, access modifiers, tooltip/label wording.\n\n"
            f"Keep your review concise. Do not explain your reasoning "
            f"at length — just report the issues in the structured output."
        )

        agent_result = agent.run_agent(
            prompt,
            system_prompt=system_prompt,
            agent_id="architect",
            allowed_tools=["Read", "Glob", "Grep"],
            output_format_schema=ReviewResult,
            max_turns=10,
            max_budget_usd=0.50,
            cwd=_resolve_cwd(settings, state),
            on_event=on_event,
        )

        current_cost = state.get("total_cost_usd") or 0.0
        new_cost, budget_msg = accumulate_cost(current_cost, agent_result, settings)

        # Parse structured output from the agent session.
        if agent_result.is_error or agent_result.structured_output is None:
            result = ReviewResult(issues=[], overall_assessment="Agent error — no review")
        elif isinstance(agent_result.structured_output, ReviewResult):
            result = agent_result.structured_output
        else:
            result = ReviewResult.model_validate(agent_result.structured_output)

        # Cap and truncate: keep at most _MAX_ISSUES, sorted by severity.
        _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_issues = sorted(
            result.issues,
            key=lambda i: _SEVERITY_ORDER.get(i.severity, 4),
        )[:_MAX_ISSUES]

        new_issues: list[CodeReviewIssue] = [
            {
                "severity": issue.severity,
                "file": issue.file,
                "line": issue.line if issue.line else None,
                "description": issue.description[:_MAX_ISSUE_DESC],
                "fix_required": issue.fix_required,
            }
            for issue in sorted_issues
        ]

        medium_plus = [
            i for i in new_issues if i["severity"] in _MEDIUM_OR_ABOVE
        ]
        log_entry: ExecutionLogEntry = {
            "timestamp": now,
            "node": NODE_NAME,
            "message": (
                f"Code review found {len(result.issues)} issue(s), "
                f"kept top {len(new_issues)} "
                f"({len(medium_plus)} medium+). "
                f"Assessment: {result.overall_assessment}"
            ),
            "dry_run": settings.dry_run,
        }

        if budget_msg:
            return {
                "code_review_issues": new_issues,
                "failure_state": budget_msg,
                "total_cost_usd": new_cost,
                "execution_log": [log_entry],
            }

        return {
            "code_review_issues": new_issues,
            "total_cost_usd": new_cost,
            "execution_log": [log_entry],
        }

    return code_review


def _blocking_threshold(loop_count: int) -> set[str]:
    """Return the severity set that blocks progress at this loop iteration.

    Progressive leniency: loop 0 blocks on medium+, loop 1 on high+,
    loop 2+ on critical only.  This guarantees convergence.
    """
    idx = min(loop_count, len(_BLOCKING_THRESHOLDS) - 1)
    return _BLOCKING_THRESHOLDS[idx]


def make_review_router(
    settings: Settings,
) -> Callable[[OrchestratorState], str]:
    """
    Conditional edge after code_review.

    Uses progressive leniency:
    - Loop 0: medium+ issues → dev_story_fix_loop
    - Loop 1: high+ issues   → dev_story_fix_loop
    - Loop 2+: critical only  → dev_story_fix_loop
    - Loops exhausted with blocking issues → fail_with_state
    - No blocking issues → commit_and_push
    """

    def route(state: OrchestratorState) -> str:
        # Short-circuit: if a previous node already set failure_state
        # (e.g. fix loop detected an infrastructure failure), skip
        # directly to fail_with_state.
        if state.get("failure_state"):
            return "fail_with_state"

        issues = state["code_review_issues"]
        loop_count = state["review_loop_count"]
        tests_passing = state.get("tests_passing")

        # Tests must pass before we can commit
        if tests_passing is False:
            logger.warning(
                "tests_failing_route_to_fix",
                loop=loop_count,
                max_loops=settings.max_review_loops,
            )
            if loop_count < settings.max_review_loops:
                return "dev_story_fix_loop"
            return "fail_with_state"

        threshold = _blocking_threshold(loop_count)
        blocking = [i for i in issues if i["severity"] in threshold]
        if blocking:
            if loop_count < settings.max_review_loops:
                return "dev_story_fix_loop"
            return "fail_with_state"
        return "e2e_automation"

    return route


def make_fail_with_state_node(
    settings: Settings,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Terminal node: sets failure_state so the CLI reports the failure clearly.

    Also generates an architect diagnostic via Claude to help with the next retry.
    """

    def fail_with_state(state: OrchestratorState) -> dict[str, Any]:
        issues = state["code_review_issues"]
        loop_count = state["review_loop_count"]
        tests_passing = state.get("tests_passing")
        test_failure_output = state.get("test_failure_output") or ""
        threshold = _blocking_threshold(loop_count)
        blocking = [
            i for i in issues if i["severity"] in threshold
        ]

        parts: list[str] = []
        if tests_passing is False:
            parts.append("Tests are FAILING.")
        if blocking:
            parts.append(
                f"{len(blocking)} unresolved issue(s): "
                + "; ".join(
                    f"[{i['severity']}] {i['file']}: {i['description']}"
                    for i in blocking[:3]
                )
            )
        message = (
            f"Pipeline failed after {loop_count} loop(s). "
            + " ".join(parts)
        )

        # Generate architect diagnostic for the draft PR
        diagnostic = _generate_failure_diagnostic(
            blocking, test_failure_output, loop_count,
        )

        log_entry: ExecutionLogEntry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": "fail_with_state",
            "message": message,
            "dry_run": settings.dry_run,
        }
        logger.error("review_loop_exhausted", message=message)
        return {
            "failure_state": message,
            "failure_diagnostic": diagnostic,
            "execution_log": [log_entry],
        }

    return fail_with_state


def _generate_failure_diagnostic(
    blocking_issues: list[Any],
    test_failure_output: str,
    loop_count: int,
) -> str:
    """Build a structured diagnostic string from the failure context.

    This is a deterministic summary (no LLM call) to keep the node fast and
    side-effect-free.  The draft PR body uses this to help the next retry.
    """
    lines: list[str] = []
    lines.append(f"Pipeline exhausted after {loop_count} review loop(s).")

    if blocking_issues:
        lines.append("")
        lines.append("### Unresolved Issues")
        for issue in blocking_issues[:5]:
            sev = issue["severity"].upper()
            desc = issue["description"][:200]
            lines.append(f"- **[{sev}]** `{issue['file']}`: {desc}")

    if test_failure_output:
        lines.append("")
        lines.append("### Test Failures")
        # Cap output to keep PR body within limits
        trimmed = test_failure_output[:1500]
        if len(test_failure_output) > 1500:
            trimmed += "\n… (truncated)"
        lines.append(f"```\n{trimmed}\n```")

    lines.append("")
    lines.append("### Recommended Next Steps")
    lines.append("- Review the issues above and provide `--guidance` on the next run")
    lines.append(
        "- Re-run with the same `branch` input to continue from this code state"
    )

    return "\n".join(lines)
