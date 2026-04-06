from __future__ import annotations

from unittest.mock import patch

from bmad_orchestrator.nodes.validate_environment import make_validate_environment_node
from tests.conftest import make_state


def test_validate_env_dry_run_skips(settings):
    """Dry run should skip validation and return a log entry."""
    node = make_validate_environment_node(settings)
    result = node(make_state())
    assert result["execution_log"][0]["message"].startswith("Skipped")
    assert "failure_state" not in result


@patch(
    "bmad_orchestrator.nodes.validate_environment.run_project_command",
    return_value=(True, "ok"),
)
def test_validate_env_all_pass(mock_cmd, settings, tmp_path, monkeypatch):
    """All setup, build, and test commands pass."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    node = make_validate_environment_node(non_dry)
    result = node(make_state(
        setup_commands=["npm install"],
        build_commands=["npm run build"],
        test_commands=["npm run test"],
    ))
    assert "failure_state" not in result
    assert "Environment validated" in result["execution_log"][0]["message"]
    assert mock_cmd.call_count == 3


@patch(
    "bmad_orchestrator.nodes.validate_environment.run_project_command",
    return_value=(True, "ok"),
)
def test_validate_env_no_commands_passes(mock_cmd, settings, tmp_path, monkeypatch):
    """Empty command lists should pass without running anything."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    node = make_validate_environment_node(non_dry)
    result = node(make_state())
    assert "failure_state" not in result
    mock_cmd.assert_not_called()


@patch(
    "bmad_orchestrator.nodes.validate_environment.run_project_command",
    return_value=(False, "ENOENT: npm not found"),
)
def test_validate_env_setup_fails_returns_failure_state(
    mock_cmd, settings, tmp_path, monkeypatch,
):
    """Setup command failure should set failure_state."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    node = make_validate_environment_node(non_dry)
    result = node(make_state(
        setup_commands=["npm install"],
        build_commands=["npm run build"],
    ))
    assert result["failure_state"].startswith("Baseline setup failed")
    # Build should not run after setup failure
    assert mock_cmd.call_count == 1


@patch("bmad_orchestrator.nodes.validate_environment.run_project_command")
def test_validate_env_build_fails_returns_failure_state(
    mock_cmd, settings, tmp_path, monkeypatch,
):
    """Build failure after successful setup should set failure_state."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)

    def side_effect(cmd, cwd):
        if "install" in cmd:
            return True, "ok"
        return False, "error TS6053: File not found"

    mock_cmd.side_effect = side_effect
    node = make_validate_environment_node(non_dry)
    result = node(make_state(
        setup_commands=["npm install"],
        build_commands=["npm run build"],
        test_commands=["npm run test"],
    ))
    assert "Baseline build failed" in result["failure_state"]
    # setup + build, test should not run
    assert mock_cmd.call_count == 2


@patch("bmad_orchestrator.nodes.validate_environment.run_project_command")
def test_validate_env_test_fails_returns_failure_state(
    mock_cmd, settings, tmp_path, monkeypatch,
):
    """Test failure after successful setup+build should set failure_state."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)

    def side_effect(cmd, cwd):
        if "test" in cmd:
            return False, "FAIL: 2 tests failed"
        return True, "ok"

    mock_cmd.side_effect = side_effect
    node = make_validate_environment_node(non_dry)
    result = node(make_state(
        setup_commands=["npm install"],
        build_commands=["npm run build"],
        test_commands=["npm run test"],
    ))
    assert "Baseline test failed" in result["failure_state"]
    assert mock_cmd.call_count == 3


@patch(
    "bmad_orchestrator.nodes.validate_environment.run_project_command",
    return_value=(True, "ok"),
)
def test_validate_env_runs_commands_in_order(mock_cmd, settings, tmp_path, monkeypatch):
    """Commands should run in order: setup → build → test."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    node = make_validate_environment_node(non_dry)
    node(make_state(
        setup_commands=["dotnet restore"],
        build_commands=["dotnet build"],
        test_commands=["dotnet test"],
    ))
    calls = [c[0][0] for c in mock_cmd.call_args_list]
    assert calls == ["dotnet restore", "dotnet build", "dotnet test"]


@patch(
    "bmad_orchestrator.nodes.validate_environment.run_project_command",
    return_value=(True, "ok"),
)
def test_validate_env_fallback_setup_from_package_json(
    mock_cmd, settings, tmp_path, monkeypatch,
):
    """When all commands are empty, detect setup from package.json."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "package.json").write_text('{"name": "test"}')
    node = make_validate_environment_node(non_dry)
    result = node(make_state())
    # Should have run npm install as fallback
    assert mock_cmd.call_count == 1
    assert mock_cmd.call_args_list[0][0][0] == "npm install"
    assert "failure_state" not in result


@patch(
    "bmad_orchestrator.nodes.validate_environment.run_project_command",
    return_value=(True, "ok"),
)
def test_validate_env_fallback_prefers_lockfile(
    mock_cmd, settings, tmp_path, monkeypatch,
):
    """yarn.lock should trigger yarn install over npm install."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "package.json").write_text('{"name": "test"}')
    (tmp_path / "yarn.lock").write_text("")
    node = make_validate_environment_node(non_dry)
    node(make_state())
    assert mock_cmd.call_args_list[0][0][0] == "yarn install"
