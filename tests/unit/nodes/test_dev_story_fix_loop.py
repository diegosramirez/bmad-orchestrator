from __future__ import annotations

from bmad_orchestrator.nodes.dev_story_fix_loop import make_fix_loop_node
from bmad_orchestrator.services.claude_agent_service import AgentResult
from tests.conftest import make_state


def test_increments_review_loop_count(settings, mock_agent_service):
    node = make_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        review_loop_count=1,
        code_review_issues=[
            {"severity": "high", "file": "x.py", "line": 1,
             "description": "Bug", "fix_required": True},
        ],
    ))
    assert result["review_loop_count"] == 2


def test_clears_code_review_issues_after_fix(settings, mock_agent_service):
    node = make_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        review_loop_count=0,
        code_review_issues=[
            {"severity": "medium", "file": "x.py", "line": 5,
             "description": "Nit", "fix_required": True},
        ],
    ))
    assert result["code_review_issues"] == []


def test_logs_fix_loop_iteration(settings, mock_agent_service):
    node = make_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        review_loop_count=2,
        code_review_issues=[
            {"severity": "critical", "file": "x.py", "line": 1,
             "description": "RCE", "fix_required": True},
        ],
    ))
    assert "3" in result["execution_log"][0]["message"]


def test_returns_touched_files_from_agent(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["src/fixed.ts"],
    )
    node = make_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        code_review_issues=[
            {"severity": "high", "file": "src/fixed.ts", "line": 1,
             "description": "Bug", "fix_required": True},
        ],
    ))
    assert result["touched_files"] == ["src/fixed.ts"]


def test_agent_error_returns_failure_state(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=True,
        result_text="Agent session crashed",
    )
    node = make_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        code_review_issues=[
            {"severity": "high", "file": "x.ts", "line": 1,
             "description": "Bug", "fix_required": True},
        ],
    ))
    assert result["failure_state"] == "Agent session crashed"
    assert result["review_loop_count"] == 1
    assert result["code_review_issues"] == []


def test_issues_text_included_in_prompt(settings, mock_agent_service):
    node = make_fix_loop_node(mock_agent_service, settings)
    node(make_state(
        code_review_issues=[
            {"severity": "high", "file": "auth.py", "line": 10,
             "description": "SQL injection risk", "fix_required": True},
        ],
    ))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "SQL injection risk" in prompt
    assert "auth.py" in prompt


def test_touched_files_listed_in_prompt(settings, mock_agent_service):
    node = make_fix_loop_node(mock_agent_service, settings)
    node(make_state(
        touched_files=["src/app.ts", "src/service.ts"],
        code_review_issues=[
            {"severity": "medium", "file": "src/app.ts", "line": 1,
             "description": "Bug", "fix_required": True},
        ],
    ))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "src/app.ts" in prompt
    assert "src/service.ts" in prompt


def test_test_failure_output_included_in_prompt(settings, mock_agent_service):
    """When test_failure_output is set, it should appear in the prompt."""
    node = make_fix_loop_node(mock_agent_service, settings)
    node(make_state(
        test_failure_output="FAIL: snippet-list.component.spec.ts > should have link",
        code_review_issues=[
            {"severity": "high", "file": "x.ts", "line": 1,
             "description": "Bug", "fix_required": True},
        ],
    ))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "TEST FAILURES" in prompt
    assert "snippet-list.component.spec.ts" in prompt


def test_fix_loop_runs_independent_tests(
    settings, mock_agent_service, tmp_path, monkeypatch,
):
    """Non-dry-run fix loop should run _run_all_checks and set tests_passing."""
    from unittest.mock import patch

    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    node = make_fix_loop_node(mock_agent_service, non_dry)
    with patch(
        "bmad_orchestrator.nodes.dev_story_fix_loop._run_all_checks",
        return_value="Test failed: 1 failing",
    ):
        result = node(make_state(
            code_review_issues=[
                {"severity": "high", "file": "x.ts", "line": 1,
                 "description": "Bug", "fix_required": True},
            ],
        ))
    assert result["tests_passing"] is False
    assert result["test_failure_output"] == "Test failed: 1 failing"


def test_fix_loop_env_failure_sets_failure_state(
    settings, mock_agent_service, tmp_path, monkeypatch,
):
    """When agent touches 0 files and checks fail, set failure_state."""
    from unittest.mock import patch

    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    # Agent returns no touched files
    mock_agent_service.run_agent.return_value = AgentResult(touched_files=[])
    node = make_fix_loop_node(mock_agent_service, non_dry)
    with patch(
        "bmad_orchestrator.nodes.dev_story_fix_loop._run_all_checks",
        return_value="Build failed (`make setup`): Docker not running",
    ):
        result = node(make_state(
            code_review_issues=[
                {"severity": "high", "file": "x.ts", "line": 1,
                 "description": "Bug", "fix_required": True},
            ],
        ))
    assert result["failure_state"] is not None
    assert "infrastructure" in result["failure_state"].lower()
    assert result["tests_passing"] is False


def test_fix_loop_no_env_failure_when_agent_touched_files(
    settings, mock_agent_service, tmp_path, monkeypatch,
):
    """When agent touches files but checks still fail, no failure_state."""
    from unittest.mock import patch

    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["src/fix.ts"],
    )
    node = make_fix_loop_node(mock_agent_service, non_dry)
    with patch(
        "bmad_orchestrator.nodes.dev_story_fix_loop._run_all_checks",
        return_value="Test failed: 1 failing",
    ):
        result = node(make_state(
            code_review_issues=[
                {"severity": "high", "file": "x.ts", "line": 1,
                 "description": "Bug", "fix_required": True},
            ],
        ))
    assert "failure_state" not in result
    assert result["tests_passing"] is False
