from __future__ import annotations

import json

from bmad_orchestrator.nodes.code_review import (
    ReviewIssueItem,
    ReviewResult,
    make_code_review_node,
    make_review_router,
)
from bmad_orchestrator.services.claude_agent_service import AgentResult
from tests.conftest import make_state


def _make_agent_result(issues: list[ReviewIssueItem]) -> AgentResult:
    review = ReviewResult(issues=issues, overall_assessment="Needs work")
    return AgentResult(
        structured_output=review,
    )


def test_router_routes_to_fix_loop_when_medium_issues_and_below_max(settings):
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[{
            "severity": "medium", "file": "x.py", "line": 1,
            "description": "Bug", "fix_required": True,
        }],
    )
    assert router(state) == "dev_story_fix_loop"


def test_router_routes_to_commit_when_no_medium_issues(settings):
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[{
            "severity": "low", "file": "x.py", "line": 1,
            "description": "Style", "fix_required": False,
        }],
    )
    assert router(state) == "commit_and_push"


def test_router_routes_to_fail_at_max_loops_with_issues(settings):
    router = make_review_router(settings)
    # max_review_loops defaults to 2; at loop_count == 2 WITH issues → fail
    state = make_state(
        review_loop_count=2,
        code_review_issues=[{
            "severity": "critical", "file": "x.py", "line": 1,
            "description": "Bad", "fix_required": True,
        }],
    )
    assert router(state) == "fail_with_state"


def test_router_routes_to_commit_at_max_loops_no_issues(settings):
    router = make_review_router(settings)
    # At max loops but NO medium+ issues → still commit
    state = make_state(review_loop_count=2, code_review_issues=[])
    assert router(state) == "commit_and_push"


def test_router_routes_to_commit_on_empty_issues(settings):
    router = make_review_router(settings)
    state = make_state(review_loop_count=0, code_review_issues=[])
    assert router(state) == "commit_and_push"


def test_code_review_node_appends_issues(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = _make_agent_result([
        ReviewIssueItem(severity="high", file="auth.py", description="SQL injection"),
    ])

    node = make_code_review_node(mock_agent_service, settings)
    result = node(make_state())

    assert len(result["code_review_issues"]) == 1
    assert result["code_review_issues"][0]["severity"] == "high"
    assert len(result["execution_log"]) == 1


def test_code_review_node_dry_run_returns_empty_issues(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = _make_agent_result([])

    node = make_code_review_node(mock_agent_service, settings)
    result = node(make_state())
    assert result["code_review_issues"] == []


def test_code_review_agent_error_returns_empty_issues(settings, mock_agent_service):
    """When the agent session errors, code_review returns no issues."""
    mock_agent_service.run_agent.return_value = AgentResult(is_error=True)

    node = make_code_review_node(mock_agent_service, settings)
    result = node(make_state())
    assert result["code_review_issues"] == []
    assert "Agent error" in result["execution_log"][0]["message"]


# ── ReviewResult stringified-JSON validator ──────────────────────────────────

def test_review_result_parses_stringified_issues():
    """ReviewResult should handle issues arriving as a JSON string."""
    raw = json.dumps([
        {"severity": "high", "file": "auth.py", "description": "No input validation"},
    ])
    result = ReviewResult(issues=raw, overall_assessment="Needs work")
    assert len(result.issues) == 1
    assert result.issues[0].severity == "high"


# ── project_context injection ─────────────────────────────────────────────────

def test_project_context_injected_into_review_prompt(
    settings, mock_agent_service, tmp_path, monkeypatch,
):
    """project_context must appear in the architect's review prompt."""
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = _make_agent_result([])
    node = make_code_review_node(mock_agent_service, settings)
    node(make_state(project_context="=== Project Context ===\nFramework: Angular (TypeScript)"))
    call_kwargs = mock_agent_service.run_agent.call_args
    assert "Angular" in call_kwargs.args[0]  # First positional arg = prompt


def test_touched_files_listed_in_prompt(
    settings, mock_agent_service, tmp_path, monkeypatch,
):
    """Touched files should be listed in the review prompt for the agent to Read."""
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = _make_agent_result([])
    node = make_code_review_node(mock_agent_service, settings)
    node(make_state(touched_files=["src/app.ts", "src/app.html"]))
    call_kwargs = mock_agent_service.run_agent.call_args
    prompt = call_kwargs.args[0]
    assert "src/app.ts" in prompt
    assert "src/app.html" in prompt


def test_code_review_uses_read_only_tools(settings, mock_agent_service):
    """Code review should only use read-only tools — no Write/Edit/Bash."""
    mock_agent_service.run_agent.return_value = _make_agent_result([])
    node = make_code_review_node(mock_agent_service, settings)
    node(make_state())
    call_kwargs = mock_agent_service.run_agent.call_args.kwargs
    assert "Write" not in call_kwargs["allowed_tools"]
    assert "Edit" not in call_kwargs["allowed_tools"]
    assert "Bash" not in call_kwargs["allowed_tools"]
    assert "Read" in call_kwargs["allowed_tools"]


# ── Router: tests_passing gate ───────────────────────────────────────────────

def test_router_tests_failing_routes_to_fix_loop(settings):
    """When tests_passing=False and loops remain, route to fix loop."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[],
        tests_passing=False,
    )
    assert router(state) == "dev_story_fix_loop"


def test_router_tests_failing_at_max_loops_routes_to_fail(settings):
    """When tests_passing=False and max loops exhausted, route to fail."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=2,
        code_review_issues=[],
        tests_passing=False,
    )
    assert router(state) == "fail_with_state"


def test_router_tests_passing_none_treated_as_ok(settings):
    """When tests_passing=None (pre-QA), don't block commit."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[],
        tests_passing=None,
    )
    assert router(state) == "commit_and_push"


def test_router_tests_passing_true_with_no_issues_commits(settings):
    """When tests pass and no issues, commit."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[],
        tests_passing=True,
    )
    assert router(state) == "commit_and_push"


# ── fail_with_state mentions test failures ───────────────────────────────────

def test_fail_with_state_mentions_test_failures(settings):
    from bmad_orchestrator.nodes.code_review import make_fail_with_state_node
    node = make_fail_with_state_node(settings)
    result = node(make_state(
        review_loop_count=2,
        code_review_issues=[],
        tests_passing=False,
    ))
    assert "Tests are FAILING" in result["failure_state"]


def test_fail_with_state_mentions_both_tests_and_issues(settings):
    from bmad_orchestrator.nodes.code_review import make_fail_with_state_node
    node = make_fail_with_state_node(settings)
    result = node(make_state(
        review_loop_count=2,
        code_review_issues=[{
            "severity": "critical", "file": "x.py", "line": 1,
            "description": "RCE vuln", "fix_required": True,
        }],
        tests_passing=False,
    ))
    assert "Tests are FAILING" in result["failure_state"]
    assert "RCE vuln" in result["failure_state"]


# ── Router: failure_state short-circuit ──────────────────────────────────────

def test_router_failure_state_routes_to_fail(settings):
    """When failure_state is set (e.g. infra failure), route to fail immediately."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[],
        tests_passing=False,
        failure_state="Infrastructure failure: Docker not running",
    )
    assert router(state) == "fail_with_state"


# ── fail_with_state generates failure_diagnostic ──────────────────────────────

def test_fail_with_state_returns_failure_diagnostic(settings):
    """fail_with_state should return a failure_diagnostic string."""
    from bmad_orchestrator.nodes.code_review import make_fail_with_state_node
    node = make_fail_with_state_node(settings)
    result = node(make_state(
        review_loop_count=2,
        code_review_issues=[{
            "severity": "critical", "file": "src/app.ts", "line": 42,
            "description": "Missing error handling for API calls",
            "fix_required": True,
        }],
        tests_passing=False,
        test_failure_output="Error: Cannot read property 'subscribe' of undefined",
    ))
    diag = result["failure_diagnostic"]
    assert diag is not None
    assert "Unresolved Issues" in diag
    assert "src/app.ts" in diag
    assert "Test Failures" in diag
    assert "subscribe" in diag
    assert "Recommended Next Steps" in diag


def test_fail_with_state_diagnostic_without_test_failures(settings):
    """Diagnostic omits test section when tests_passing is not False."""
    from bmad_orchestrator.nodes.code_review import make_fail_with_state_node
    node = make_fail_with_state_node(settings)
    result = node(make_state(
        review_loop_count=2,
        code_review_issues=[{
            "severity": "critical", "file": "db.py", "line": 1,
            "description": "SQL injection", "fix_required": True,
        }],
    ))
    diag = result["failure_diagnostic"]
    assert "Unresolved Issues" in diag
    assert "Test Failures" not in diag
