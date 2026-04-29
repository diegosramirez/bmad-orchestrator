from __future__ import annotations

from unittest.mock import patch

from bmad_orchestrator.nodes.dev_story import (
    ChecklistCompletionAssessment,
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
def test_run_all_checks_runs_setup_commands(mock_cmd, mock_compile, tmp_path):
    """Setup commands run before build commands."""
    _run_all_checks(["npm run build"], [], [], tmp_path, setup_commands=["npm install"])
    assert mock_cmd.call_count == 2
    assert mock_cmd.call_args_list[0][0] == ("npm install", tmp_path)
    assert mock_cmd.call_args_list[1][0] == ("npm run build", tmp_path)


@patch("bmad_orchestrator.nodes.dev_story.run_compile_check", return_value=[])
@patch("bmad_orchestrator.nodes.dev_story.run_project_command", return_value=(True, "ok"))
def test_run_all_checks_no_setup_commands_skips_setup(mock_cmd, mock_compile, tmp_path):
    """Without setup_commands, only build/test/lint commands run."""
    _run_all_checks(["npm run build"], [], [], tmp_path)
    assert mock_cmd.call_count == 1
    assert mock_cmd.call_args_list[0][0] == ("npm run build", tmp_path)


@patch("bmad_orchestrator.nodes.dev_story.run_compile_check", return_value=[])
@patch(
    "bmad_orchestrator.nodes.dev_story.run_project_command",
    return_value=(False, "ENOENT: dotnet not found"),
)
def test_run_all_checks_setup_failure_returns_error(mock_cmd, mock_compile, tmp_path):
    """If a setup command fails, return an error string immediately."""
    result = _run_all_checks([], [], [], tmp_path, setup_commands=["dotnet restore"])
    assert result is not None
    assert "Setup failed" in result
    assert "dotnet restore" in result


# ── dev_story node with Agent SDK ─────────────────────────────────────────────

def test_dev_story_returns_touched_files(settings, mock_agent_service, mock_claude, mock_jira):
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["src/app.ts", "src/app.html"],
    )
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    result = node(make_state())
    assert result["touched_files"] == ["src/app.ts", "src/app.html"]
    assert len(result["execution_log"]) == 1


def test_dev_story_agent_error_returns_failure_state(
    settings, mock_agent_service, mock_claude, mock_jira
):
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=True,
        result_text="Session crashed",
    )
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    result = node(make_state())
    assert result["failure_state"] == "Session crashed"
    assert len(result["execution_log"]) == 2


def test_dev_story_injects_project_context(settings, mock_agent_service, mock_claude, mock_jira):
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state(project_context="Framework: Angular (TypeScript)"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Angular" in prompt


def test_dev_story_includes_verification_commands(
    settings, mock_agent_service, mock_claude, mock_jira
):
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state(build_commands=["npm run build"], test_commands=["npm test"]))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "npm run build" in prompt
    assert "npm test" in prompt


def test_dev_story_includes_guidelines(settings, mock_agent_service, mock_claude, mock_jira):
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state(dev_guidelines="Use strict TypeScript"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Use strict TypeScript" in prompt


def test_dev_story_includes_jira_checklist_in_prompt(
    settings, mock_agent_service, mock_claude, mock_jira
):
    mock_jira.get_story_checklist_text.return_value = "* [ ] **Step one** — do it"
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state(current_story_id="PROJ-1"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Implementation checklist (from Jira)" in prompt
    assert "Step one" in prompt
    mock_jira.get_story_checklist_text.assert_called_once_with("PROJ-1")


def test_dev_story_updates_checklist_after_success(
    settings, mock_agent_service, mock_claude, mock_jira
):
    """Non-dry-run: complete_structured marks items; set_story_checklist_text receives [x]."""
    non_dry = settings.model_copy(update={"dry_run": False})
    mock_jira.get_story_checklist_text.return_value = "* [ ] **Alpha** — first"
    mock_agent_service.run_agent.return_value = AgentResult(
        touched_files=["a.ts"],
        result_text="Implemented Alpha.",
    )
    mock_claude.complete_structured.return_value = ChecklistCompletionAssessment(
        completed_task_summaries=["Alpha"],
    )
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, non_dry)
    node(make_state(current_story_id="PROJ-9", acceptance_criteria=["AC1"]))
    mock_claude.complete_structured.assert_called_once()
    mock_jira.set_story_checklist_text.assert_called_once()
    updated = mock_jira.set_story_checklist_text.call_args[0][1]
    assert "* [x] **Alpha**" in updated


def test_dev_story_skips_checklist_sync_when_empty(
    settings, mock_agent_service, mock_claude, mock_jira
):
    mock_jira.get_story_checklist_text.return_value = ""
    mock_agent_service.run_agent.return_value = AgentResult(touched_files=["x.ts"])
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state(current_story_id="PROJ-1"))
    mock_claude.complete_structured.assert_not_called()
    mock_jira.set_story_checklist_text.assert_not_called()


def _figma_settings_update():
    from pydantic import SecretStr

    return {
        "figma_mcp_enabled": True,
        "figma_mcp_token": SecretStr("figd_test"),
    }


def test_dev_story_injects_figma_block_when_enabled(
    settings, mock_agent_service, mock_claude, mock_jira
):
    figma_settings = settings.model_copy(update=_figma_settings_update())
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, figma_settings)
    node(make_state(figma_url="https://www.figma.com/design/abc/Home"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Figma design reference" in prompt
    assert "https://www.figma.com/design/abc/Home" in prompt
    assert "mcp__figma__" in prompt


def test_dev_story_falls_back_to_story_content_for_figma_url(
    settings, mock_agent_service, mock_claude, mock_jira
):
    figma_settings = settings.model_copy(update=_figma_settings_update())
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, figma_settings)
    node(
        make_state(
            story_content="See https://www.figma.com/file/xyz for the layout",
        )
    )
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "https://www.figma.com/file/xyz" in prompt


def test_dev_story_omits_figma_block_when_mcp_disabled(
    settings, mock_agent_service, mock_claude, mock_jira
):
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state(figma_url="https://www.figma.com/design/abc/Home"))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "Figma design reference" not in prompt


def test_dev_story_passes_figma_mcp_servers_when_enabled(
    settings, mock_agent_service, mock_claude, mock_jira
):
    figma_settings = settings.model_copy(update=_figma_settings_update())
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, figma_settings)
    node(make_state())
    kwargs = mock_agent_service.run_agent.call_args.kwargs
    assert kwargs["mcp_servers"] == {
        "figma": {
            "type": "http",
            "url": "https://mcp.figma.com/mcp",
            "headers": {"Authorization": "Bearer figd_test"},
        }
    }


def test_dev_story_passes_no_mcp_servers_when_disabled(
    settings, mock_agent_service, mock_claude, mock_jira
):
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state())
    kwargs = mock_agent_service.run_agent.call_args.kwargs
    assert kwargs["mcp_servers"] is None


def test_dev_story_includes_ux_handoff_block(
    settings, mock_agent_service, mock_claude, mock_jira
):
    node = make_dev_story_node(mock_agent_service, mock_claude, mock_jira, settings)
    node(make_state(ux_handoff="## UX design handoff\n\nBuild the login form."))
    prompt = mock_agent_service.run_agent.call_args.args[0]
    assert "UX design handoff" in prompt
    assert "Build the login form." in prompt
