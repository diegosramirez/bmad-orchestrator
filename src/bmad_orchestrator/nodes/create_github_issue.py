from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.protocols import GitHubServiceProtocol, JiraServiceProtocol
from bmad_orchestrator.state import OrchestratorState
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

NODE_NAME = "create_github_issue"

_ISSUE_BODY_TEMPLATE = """\
## Story

**Jira:** {jira_link}

{story_content}

## Acceptance Criteria

{acceptance_criteria}

## Architecture Notes

{architect_output}

## Implementation Plan

{developer_output}

## Test Expectations

{qa_scope}

## Build / Lint / Test Commands

{commands}

## Scope Constraints

{constraints}

---
*Created by BMAD Autonomous Engineering Orchestrator* 🤖

{metadata}
"""


def _format_list(items: list[str] | None, fallback: str = "- N/A") -> str:
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items)


def _format_commands(
    build: list[str], test: list[str], lint: list[str],
) -> str:
    lines: list[str] = []
    if build:
        lines.append("**Build:**")
        lines.extend(f"```\n{cmd}\n```" for cmd in build)
    if test:
        lines.append("**Test:**")
        lines.extend(f"```\n{cmd}\n```" for cmd in test)
    if lint:
        lines.append("**Lint:**")
        lines.extend(f"```\n{cmd}\n```" for cmd in lint)
    return "\n".join(lines) if lines else "- No commands configured"


def make_create_github_issue_node(
    github: GitHubServiceProtocol,
    jira: JiraServiceProtocol,
    settings: Settings,
) -> Callable[[OrchestratorState], dict[str, Any]]:

    def create_github_issue(state: OrchestratorState) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()

        # Idempotency: skip if issue already created
        if state.get("github_issue_url"):
            return {
                "github_issue_url": state["github_issue_url"],
                "github_issue_number": state["github_issue_number"],
                "execution_log": [{
                    "timestamp": now,
                    "node": NODE_NAME,
                    "message": f"GitHub Issue already exists: {state['github_issue_url']}",
                    "dry_run": settings.dry_run,
                }],
            }

        story_id = state.get("current_story_id") or "BMAD"
        team_id = state["team_id"]
        input_prompt = state["input_prompt"]

        # Build Jira link
        jira_link = story_id
        if settings.jira_base_url and story_id != "BMAD":
            jira_link = f"[{story_id}]({settings.jira_base_url}/browse/{story_id})"

        # Build issue body
        story_content = state.get("story_content") or input_prompt
        constraints_parts: list[str] = []
        if state.get("dependencies"):
            constraints_parts.append(
                "**Dependencies:**\n" + _format_list(state["dependencies"])
            )
        if state.get("definition_of_done"):
            constraints_parts.append(
                "**Definition of Done:**\n" + _format_list(state["definition_of_done"])
            )
        dev_guidelines = state.get("dev_guidelines") or ""
        if dev_guidelines:
            constraints_parts.append(f"**Dev Guidelines:**\n{dev_guidelines[:800]}")
        constraints = "\n\n".join(constraints_parts) if constraints_parts else "- None specified"

        # Hidden metadata for issue-to-code bridge (parsed by bmad-issue-executor.yml)
        code_agent = state.get("code_agent") or settings.code_agent
        metadata_lines = [
            f"<!-- bmad:target_repo={settings.github_repo or ''} -->",
            f"<!-- bmad:team_id={team_id} -->",
            f"<!-- bmad:story_key={story_id} -->",
            f"<!-- bmad:base_branch={settings.github_base_branch} -->",
        ]
        if code_agent:
            metadata_lines.append(
                f"<!-- bmad:code_agent={code_agent} -->"
            )
        metadata = "\n".join(metadata_lines)

        body = _ISSUE_BODY_TEMPLATE.format(
            jira_link=jira_link,
            story_content=story_content,
            acceptance_criteria=_format_list(state.get("acceptance_criteria")),
            architect_output=state.get("architect_output") or "- Not available",
            developer_output=state.get("developer_output") or "- Not available",
            qa_scope=_format_list(state.get("qa_scope")),
            commands=_format_commands(
                state.get("build_commands") or [],
                state.get("test_commands") or [],
                state.get("lint_commands") or [],
            ),
            constraints=constraints,
            metadata=metadata,
        )

        # GitHub hard limit is 65 536 chars
        _GITHUB_BODY_LIMIT = 65_000
        if len(body) > _GITHUB_BODY_LIMIT:
            body = body[:_GITHUB_BODY_LIMIT] + "\n\n*[Issue body truncated]*"

        title = f"[{team_id}] {input_prompt[:80]} [{story_id}]"
        labels = ["bmad-orchestrated", team_id]

        # Auto-execute: add bmad-execute label to trigger immediate code generation
        if state.get("auto_execute_issue") or settings.auto_execute_issue:
            labels.append("bmad-execute")

        url, issue_number = github.create_issue(
            title=title,
            body=body,
            labels=labels,
        )
        logger.info("github_issue_created", url=url, issue_number=issue_number)

        # Cross-link: post GitHub Issue URL as a Jira comment
        notify_key = state.get("notify_jira_story_key") or state.get("current_story_id")
        if notify_key and not settings.dry_run:
            jira.add_comment(
                notify_key,
                f"GitHub Issue created for coding agent: {url}",
            )

        return {
            "github_issue_url": url,
            "github_issue_number": issue_number,
            "execution_log": [{
                "timestamp": now,
                "node": NODE_NAME,
                "message": f"GitHub Issue created: {url}",
                "dry_run": settings.dry_run,
            }],
        }

    return create_github_issue
