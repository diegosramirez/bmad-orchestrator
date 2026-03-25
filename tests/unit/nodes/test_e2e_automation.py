from __future__ import annotations

from unittest.mock import patch

from bmad_orchestrator.nodes.e2e_automation import make_e2e_automation_node, make_e2e_router
from bmad_orchestrator.services.claude_agent_service import AgentResult
from tests.conftest import make_state


def test_e2e_defaults_to_playwright_when_no_commands(settings, mock_agent_service):
    """When no e2e_commands detected, node defaults to 'npx playwright test'."""
    node = make_e2e_automation_node(mock_agent_service, settings)
    node(make_state(e2e_commands=[]))
    mock_agent_service.run_agent.assert_called_once()
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "npx playwright test" in prompt


def test_e2e_dry_run_returns_result(settings, mock_agent_service):
    node = make_e2e_automation_node(mock_agent_service, settings)
    result = node(make_state(e2e_commands=["npx playwright test"]))
    assert result["e2e_results"][0]["test_file"] == "agent_self_verified"
    assert result["e2e_results"][0]["passed"] is True


def test_e2e_dry_run_skips_validation(settings, mock_agent_service):
    """In dry-run mode, _run_e2e_checks should NOT be called."""
    node = make_e2e_automation_node(mock_agent_service, settings)
    with patch(
        "bmad_orchestrator.nodes.e2e_automation._run_e2e_checks",
    ) as mock_checks:
        result = node(make_state(e2e_commands=["npx playwright test"]))
    mock_checks.assert_not_called()
    assert result["e2e_tests_passing"] is True


@patch("bmad_orchestrator.nodes.e2e_automation._run_e2e_checks", return_value=None)
def test_e2e_real_run_tests_pass(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["e2e/auth.spec.ts"],
        result_text="All E2E tests passed",
    )
    node = make_e2e_automation_node(mock_agent_service, non_dry)
    result = node(make_state(e2e_commands=["npx playwright test"]))

    assert result["e2e_tests_passing"] is True
    assert result["e2e_failure_output"] is None
    assert "PASS" in result["execution_log"][0]["message"]


@patch(
    "bmad_orchestrator.nodes.e2e_automation._run_e2e_checks",
    return_value="E2E failed (`npx playwright test`):\n1 test failed",
)
def test_e2e_real_run_tests_fail(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult()
    node = make_e2e_automation_node(mock_agent_service, non_dry)
    result = node(make_state(e2e_commands=["npx playwright test"]))

    assert result["e2e_tests_passing"] is False
    assert "E2E failed" in result["e2e_failure_output"]
    assert "FAIL" in result["execution_log"][0]["message"]


@patch("bmad_orchestrator.nodes.e2e_automation._run_e2e_checks", return_value=None)
def test_e2e_agent_error_reported(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=True, result_text="Agent crashed",
    )
    node = make_e2e_automation_node(mock_agent_service, non_dry)
    result = node(make_state(e2e_commands=["npx playwright test"]))
    assert result["e2e_results"][0]["passed"] is False


def test_e2e_returns_touched_files(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["e2e/login.spec.ts"],
    )
    node = make_e2e_automation_node(mock_agent_service, settings)
    result = node(make_state(e2e_commands=["npx playwright test"]))
    assert result["touched_files"] == ["e2e/login.spec.ts"]


def test_e2e_prompt_includes_acceptance_criteria(settings, mock_agent_service):
    node = make_e2e_automation_node(mock_agent_service, settings)
    node(make_state(
        e2e_commands=["npx playwright test"],
        acceptance_criteria=["User can log in", "User sees dashboard"],
    ))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "User can log in" in prompt
    assert "User sees dashboard" in prompt


def test_e2e_prompt_includes_e2e_commands(settings, mock_agent_service):
    node = make_e2e_automation_node(mock_agent_service, settings)
    node(make_state(e2e_commands=["npx playwright test --project=chromium"]))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "npx playwright test --project=chromium" in prompt


# ── E2E Router Tests ─────────────────────────────────────────────────────────


def test_e2e_router_no_commands_passing_routes_to_commit(settings):
    """Even without explicit e2e_commands, router checks e2e_tests_passing."""
    router = make_e2e_router(settings)
    state = make_state(e2e_commands=[], e2e_tests_passing=True)
    assert router(state) == "commit_and_push"


def test_e2e_router_no_commands_failing_routes_to_fix(settings):
    """Without e2e_commands, failing tests still route to fix loop."""
    router = make_e2e_router(settings)
    state = make_state(e2e_commands=[], e2e_tests_passing=False, e2e_loop_count=0)
    assert router(state) == "e2e_fix_loop"


def test_e2e_router_passing_routes_to_commit(settings):
    router = make_e2e_router(settings)
    state = make_state(
        e2e_commands=["npx playwright test"],
        e2e_tests_passing=True,
    )
    assert router(state) == "commit_and_push"


def test_e2e_router_failing_with_loops_routes_to_fix(settings):
    router = make_e2e_router(settings)
    state = make_state(
        e2e_commands=["npx playwright test"],
        e2e_tests_passing=False,
        e2e_loop_count=0,
    )
    assert router(state) == "e2e_fix_loop"


def test_e2e_router_failing_exhausted_routes_to_commit(settings):
    """E2E failures are non-blocking after exhausting loops."""
    s = settings.model_copy(update={"max_e2e_loops": 1})
    router = make_e2e_router(s)
    state = make_state(
        e2e_commands=["npx playwright test"],
        e2e_tests_passing=False,
        e2e_loop_count=1,
    )
    assert router(state) == "commit_and_push"
