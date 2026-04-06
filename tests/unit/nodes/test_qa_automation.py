from __future__ import annotations

from unittest.mock import patch

from bmad_orchestrator.nodes.qa_automation import make_qa_automation_node
from bmad_orchestrator.services.claude_agent_service import AgentResult
from tests.conftest import make_state


def test_qa_automation_dry_run_returns_result(settings, mock_agent_service):
    node = make_qa_automation_node(mock_agent_service, settings)
    result = node(make_state())
    assert result["qa_results"][0]["test_file"] == "agent_self_verified"
    assert result["qa_results"][0]["passed"] is True


def test_qa_automation_dry_run_skips_independent_validation(
    settings, mock_agent_service,
):
    """In dry-run mode, _run_all_checks should NOT be called."""
    node = make_qa_automation_node(mock_agent_service, settings)
    with patch(
        "bmad_orchestrator.nodes.qa_automation._run_all_checks",
    ) as mock_checks:
        result = node(make_state())
    mock_checks.assert_not_called()
    assert result["tests_passing"] is True


@patch("bmad_orchestrator.nodes.qa_automation._run_all_checks", return_value=None)
def test_qa_automation_real_run_tests_pass(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    """Non-dry-run: when _run_all_checks returns None, tests_passing=True."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["tests/test_app.ts"],
        result_text="All tests passed",
    )
    node = make_qa_automation_node(mock_agent_service, non_dry)
    result = node(make_state(test_commands=["npx vitest run"]))

    assert result["tests_passing"] is True
    assert result["test_failure_output"] is None
    assert "PASS" in result["execution_log"][0]["message"]


@patch(
    "bmad_orchestrator.nodes.qa_automation._run_all_checks",
    return_value="Test failed (ng test): 1 failing",
)
def test_qa_automation_real_run_tests_fail(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    """Non-dry-run: when _run_all_checks returns error, tests_passing=False."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult()
    node = make_qa_automation_node(mock_agent_service, non_dry)
    result = node(make_state(test_commands=["ng test --watch=false"]))

    assert result["tests_passing"] is False
    assert result["test_failure_output"] == "Test failed (ng test): 1 failing"
    assert "FAIL" in result["execution_log"][0]["message"]


@patch("bmad_orchestrator.nodes.qa_automation._run_all_checks", return_value=None)
def test_qa_automation_no_test_commands_returns_passed(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    """When no test commands are detected, QA still returns agent result."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult()
    node = make_qa_automation_node(mock_agent_service, non_dry)
    result = node(make_state(test_commands=[]))
    assert result["qa_results"][0]["test_file"] == "agent_self_verified"
    assert result["tests_passing"] is True


def test_qa_automation_returns_touched_files(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["tests/test_auth.spec.ts"],
    )
    node = make_qa_automation_node(mock_agent_service, settings)
    result = node(make_state())
    assert result["touched_files"] == ["tests/test_auth.spec.ts"]


def test_qa_automation_injects_project_context_into_prompt(
    settings, mock_agent_service,
):
    """QA prompt should include project context from state."""
    node = make_qa_automation_node(mock_agent_service, settings)
    node(make_state(project_context="Framework: Angular (TypeScript)\nTest runner: Vitest"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Angular" in prompt
    assert "Vitest" in prompt


def test_qa_automation_lists_implementation_files_in_prompt(
    settings, mock_agent_service,
):
    """QA prompt should list the implementation files to test."""
    node = make_qa_automation_node(mock_agent_service, settings)
    node(make_state(touched_files=["src/app.ts", "src/app.html"]))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "src/app.ts" in prompt
    assert "src/app.html" in prompt


def test_qa_automation_includes_test_commands_in_prompt(
    settings, mock_agent_service,
):
    """QA prompt should include verification test commands."""
    node = make_qa_automation_node(mock_agent_service, settings)
    node(make_state(test_commands=["npx vitest run"]))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "npx vitest run" in prompt


@patch("bmad_orchestrator.nodes.qa_automation._run_all_checks", return_value=None)
def test_qa_automation_agent_error_reported(
    mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    """Agent errors should be reported in qa_results."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=True, result_text="Agent crashed",
    )
    node = make_qa_automation_node(mock_agent_service, non_dry)
    result = node(make_state(test_commands=["npm test"]))

    assert result["qa_results"][0]["passed"] is False


@patch("bmad_orchestrator.nodes.qa_automation._run_all_checks", return_value=None)
@patch("bmad_orchestrator.nodes.qa_automation.find_example_test_file")
def test_qa_automation_injects_example_test_file(
    mock_find, mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    """QA prompt should include an existing test file as a reference pattern."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_find.return_value = "### src/app.spec.ts\n```\nimport { vi } from 'vitest';\n```"
    mock_agent_service.run_agent.return_value = AgentResult()
    node = make_qa_automation_node(mock_agent_service, non_dry)
    node(make_state(test_commands=["npm test"]))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Reference" in prompt
    assert "vitest" in prompt
    assert "EXACT same test framework" in prompt


@patch("bmad_orchestrator.nodes.qa_automation._run_all_checks", return_value=None)
@patch("bmad_orchestrator.nodes.qa_automation.find_example_test_file")
def test_qa_automation_prefers_project_test_over_dev_written(
    mock_find, mock_checks, settings, mock_agent_service, tmp_path, monkeypatch,
):
    """QA should prefer the project's own test files over dev-written specs."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_find.return_value = "### src/app/app.spec.ts\n```\ndescribe('App', () => {});\n```"
    mock_agent_service.run_agent.return_value = AgentResult()
    node = make_qa_automation_node(mock_agent_service, non_dry)
    node(make_state(
        test_commands=["npm test"],
        touched_files=["src/counter/counter.component.ts"],
    ))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Reference" in prompt
    assert "app.spec.ts" in prompt
    mock_find.assert_called_once()
