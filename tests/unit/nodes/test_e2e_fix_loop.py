from __future__ import annotations

from unittest.mock import patch

from bmad_orchestrator.nodes.e2e_fix_loop import make_e2e_fix_loop_node
from bmad_orchestrator.services.claude_agent_service import AgentResult
from tests.conftest import make_state


def test_increments_e2e_loop_count(settings, mock_agent_service):
    node = make_e2e_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        e2e_loop_count=0,
        e2e_commands=["npx playwright test"],
        e2e_failure_output="E2E failed: login test",
    ))
    assert result["e2e_loop_count"] == 1


def test_logs_fix_loop_iteration(settings, mock_agent_service):
    node = make_e2e_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        e2e_loop_count=1,
        e2e_commands=["npx playwright test"],
    ))
    assert "2" in result["execution_log"][0]["message"]


def test_returns_touched_files_from_agent(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["src/login.ts"],
    )
    node = make_e2e_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        e2e_commands=["npx playwright test"],
        e2e_failure_output="E2E failed",
    ))
    assert result["touched_files"] == ["src/login.ts"]


def test_agent_error_returns_e2e_failure(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=True,
        result_text="Agent session crashed",
    )
    node = make_e2e_fix_loop_node(mock_agent_service, settings)
    result = node(make_state(
        e2e_commands=["npx playwright test"],
        e2e_failure_output="E2E failed",
    ))
    assert result["e2e_tests_passing"] is False
    assert result["e2e_failure_output"] == "Agent session crashed"
    assert result["e2e_loop_count"] == 1


def test_e2e_failure_output_included_in_prompt(settings, mock_agent_service):
    node = make_e2e_fix_loop_node(mock_agent_service, settings)
    node(make_state(
        e2e_commands=["npx playwright test"],
        e2e_failure_output="FAIL: login.spec.ts > should navigate to dashboard",
    ))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "E2E FAILURES" in prompt
    assert "login.spec.ts" in prompt


@patch(
    "bmad_orchestrator.nodes.e2e_fix_loop._run_e2e_checks",
    return_value=None,
)
def test_fix_loop_runs_e2e_checks_pass(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    node = make_e2e_fix_loop_node(mock_agent_service, non_dry)
    result = node(make_state(
        e2e_commands=["npx playwright test"],
        e2e_failure_output="E2E failed",
    ))
    assert result["e2e_tests_passing"] is True
    assert result["e2e_failure_output"] is None


@patch(
    "bmad_orchestrator.nodes.e2e_fix_loop._run_e2e_checks",
    return_value="E2E failed (`npx playwright test`):\nstill broken",
)
def test_fix_loop_runs_e2e_checks_fail(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    node = make_e2e_fix_loop_node(mock_agent_service, non_dry)
    result = node(make_state(
        e2e_commands=["npx playwright test"],
        e2e_failure_output="E2E failed",
    ))
    assert result["e2e_tests_passing"] is False
    assert "still broken" in result["e2e_failure_output"]
