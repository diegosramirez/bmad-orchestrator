from __future__ import annotations

from unittest.mock import patch

from bmad_orchestrator.nodes.dev_story import (
    FileOperationList,
    FileOperationModel,
    _apply_operations,
    _prefix_output_dir,
    _run_all_checks,
    make_dev_story_node,
)
from bmad_orchestrator.services.claude_agent_service import AgentResult
from tests.conftest import make_state


def _op(action: str, path: str, content: str = "") -> FileOperationModel:
    """Shorthand to build a FileOperationModel."""
    return FileOperationModel(action=action, path=path, content=content)


# ── _apply_operations (non-dry-run paths) ─────────────────────────────────────

def test_apply_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ops = [_op("create", "src/foo.py", "x = 1\n")]
    touched = _apply_operations(ops, dry_run=False)
    assert (tmp_path / "src/foo.py").read_text() == "x = 1\n"
    assert "src/foo.py" in touched


def test_apply_skips_unchanged_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text("x = 1\n")
    ops = [_op("modify", "foo.py", "x = 1\n")]
    touched = _apply_operations(ops, dry_run=False)
    assert "foo.py" in touched


def test_apply_modifies_changed_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text("x = 1\n")
    ops = [_op("modify", "foo.py", "x = 2\n")]
    _apply_operations(ops, dry_run=False)
    assert (tmp_path / "foo.py").read_text() == "x = 2\n"


def test_apply_deletes_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "old.py").write_text("old content\n")
    ops = [_op("delete", "old.py")]
    _apply_operations(ops, dry_run=False)
    assert not (tmp_path / "old.py").exists()


def test_apply_delete_nonexistent_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ops = [_op("delete", "ghost.py")]
    touched = _apply_operations(ops, dry_run=False)
    assert "ghost.py" in touched


# ── _prefix_output_dir ────────────────────────────────────────────────────────

def test_prefix_output_dir_adds_story_key():
    ops = [_op("create", "src/app.py", "code")]
    prefixed = _prefix_output_dir(ops, "PROJ-42", "_bmad-output/implementation-artifacts")
    assert prefixed[0].path == "_bmad-output/implementation-artifacts/PROJ-42/src/app.py"
    assert prefixed[0].content == "code"
    assert prefixed[0].action == "create"


def test_prefix_output_dir_none_story_id_uses_unknown():
    ops = [_op("create", "index.html", "<h1>hi</h1>")]
    prefixed = _prefix_output_dir(ops, None, "_bmad-output/implementation-artifacts")
    assert prefixed[0].path == "_bmad-output/implementation-artifacts/unknown/index.html"


# ── FileOperationList validator ───────────────────────────────────────────────

def test_parse_stringified_json_with_control_chars():
    """Ensure the validator handles JSON strings with embedded newlines/tabs."""
    raw_json = '[{"action": "create", "path": "a.py", "content": "x = 1\\n\\ty = 2"}]'
    result = FileOperationList(operations=raw_json)
    assert len(result.operations) == 1
    assert result.operations[0].path == "a.py"


def test_parse_stringified_json_with_unescaped_quotes():
    """Ensure the validator repairs and parses JSON with unescaped quotes."""
    raw = '[{"action": "create", "path": "t.py", "content": "x = ""hello""\n"}]'
    result = FileOperationList(operations=raw)
    assert len(result.operations) == 1
    assert result.operations[0].path == "t.py"


# ── _run_all_checks ───────────────────────────────────────────────────────────

@patch("bmad_orchestrator.nodes.dev_story.run_compile_check", return_value=[])
@patch("bmad_orchestrator.nodes.dev_story.run_project_command", return_value=(True, "ok"))
def test_run_all_checks_all_pass(mock_cmd, mock_compile, tmp_path):
    result = _run_all_checks(["npm run build"], ["npm test"], ["npm run lint"], tmp_path)
    assert result is None


@patch("bmad_orchestrator.nodes.dev_story.run_compile_check", return_value=[])
@patch(
    "bmad_orchestrator.nodes.dev_story.run_project_command",
    return_value=(False, "error TS2304"),
)
def test_run_all_checks_build_fail_returns_string(mock_cmd, mock_compile, tmp_path):
    result = _run_all_checks(["npm run build"], [], [], tmp_path)
    assert result is not None
    assert "Build failed" in result


@patch(
    "bmad_orchestrator.nodes.dev_story.run_compile_check",
    return_value=["src/app.ts(1,1): error TS2304"],
)
def test_run_all_checks_compile_error_returns_string(mock_compile, tmp_path):
    result = _run_all_checks([], [], [], tmp_path)
    assert result is not None
    assert "TypeScript" in result


@patch("bmad_orchestrator.nodes.dev_story.run_compile_check", return_value=[])
def test_run_all_checks_no_commands_returns_none(mock_compile, tmp_path):
    assert _run_all_checks([], [], [], tmp_path) is None


@patch("bmad_orchestrator.nodes.dev_story.run_compile_check", return_value=[])
@patch("bmad_orchestrator.nodes.dev_story.run_project_command", return_value=(True, "ok"))
def test_run_all_checks_runs_npm_install_when_node_modules_missing(
    mock_cmd, mock_compile, tmp_path
):
    """npm install is run as a preflight when package.json exists but node_modules doesn't."""
    (tmp_path / "package.json").write_text('{"name": "test"}')
    _run_all_checks(["npm run build"], [], [], tmp_path)
    # First call should be npm install, second is npm run build
    assert mock_cmd.call_count == 2
    assert mock_cmd.call_args_list[0][0] == ("npm install", tmp_path)


@patch("bmad_orchestrator.nodes.dev_story.run_compile_check", return_value=[])
@patch("bmad_orchestrator.nodes.dev_story.run_project_command", return_value=(True, "ok"))
def test_run_all_checks_skips_npm_install_when_node_modules_exist(
    mock_cmd, mock_compile, tmp_path
):
    """npm install is NOT run when node_modules already exists."""
    (tmp_path / "package.json").write_text('{"name": "test"}')
    (tmp_path / "node_modules").mkdir()
    _run_all_checks(["npm run build"], [], [], tmp_path)
    # Only the build command should be called, no npm install
    assert mock_cmd.call_count == 1
    assert mock_cmd.call_args_list[0][0] == ("npm run build", tmp_path)


# ── dev_story node with Agent SDK ─────────────────────────────────────────────

def test_dev_story_returns_touched_files(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["src/app.ts", "src/app.html"],
    )
    node = make_dev_story_node(mock_agent_service, settings)
    result = node(make_state())
    assert result["touched_files"] == ["src/app.ts", "src/app.html"]
    assert len(result["execution_log"]) == 1


def test_dev_story_agent_error_returns_failure_state(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=True,
        result_text="Session crashed",
    )
    node = make_dev_story_node(mock_agent_service, settings)
    result = node(make_state())
    assert result["failure_state"] == "Session crashed"
    assert len(result["execution_log"]) == 2


def test_dev_story_injects_project_context(settings, mock_agent_service):
    node = make_dev_story_node(mock_agent_service, settings)
    node(make_state(project_context="Framework: Angular (TypeScript)"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Angular" in prompt


def test_dev_story_includes_verification_commands(settings, mock_agent_service):
    node = make_dev_story_node(mock_agent_service, settings)
    node(make_state(build_commands=["npm run build"], test_commands=["npm test"]))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "npm run build" in prompt
    assert "npm test" in prompt


def test_dev_story_includes_guidelines(settings, mock_agent_service):
    node = make_dev_story_node(mock_agent_service, settings)
    node(make_state(dev_guidelines="Use strict TypeScript"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Use strict TypeScript" in prompt
