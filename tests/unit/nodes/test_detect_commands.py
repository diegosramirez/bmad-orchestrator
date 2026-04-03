from __future__ import annotations

import json

from bmad_orchestrator.nodes.detect_commands import (
    ProjectCommands,
    make_detect_commands_node,
)
from tests.conftest import make_state


def test_detect_commands_dry_run_skips_claude_call(settings, mock_claude):
    """In dry-run mode, no Claude call is made and commands stay empty."""
    node = make_detect_commands_node(mock_claude, settings)
    result = node(make_state())
    mock_claude.complete_structured.assert_not_called()
    assert result["execution_log"][0]["message"].startswith("Skipped")


def test_detect_commands_calls_claude_and_sets_commands(settings, mock_claude):
    """Non-dry-run should call Claude and return detected commands."""
    non_dry = settings.model_copy(update={"dry_run": False})
    mock_claude.complete_structured.return_value = ProjectCommands(
        setup=["npm install"],
        build=["npm run build"],
        test=["npx vitest run"],
        lint=["npm run lint"],
        reasoning="Angular project with Vitest",
    )
    node = make_detect_commands_node(mock_claude, non_dry)
    result = node(make_state(project_context="Angular (TypeScript)"))
    assert result["setup_commands"] == ["npm install"]
    assert result["build_commands"] == ["npm run build"]
    assert result["test_commands"] == ["npx vitest run"]
    assert result["lint_commands"] == ["npm run lint"]
    assert result["e2e_commands"] == []
    assert len(result["execution_log"]) == 1


def test_detect_commands_includes_project_context_in_prompt(settings, mock_claude):
    """The Claude prompt should include the project context from state."""
    non_dry = settings.model_copy(update={"dry_run": False})
    mock_claude.complete_structured.return_value = ProjectCommands(
        build=[], test=[], lint=[], reasoning="",
    )
    node = make_detect_commands_node(mock_claude, non_dry)
    node(make_state(project_context="Framework: React (TypeScript)"))
    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    assert "React" in call_kwargs["user_message"]


def test_detect_commands_includes_manifest_scripts(
    settings, mock_claude, tmp_path, monkeypatch,
):
    """Raw package.json scripts should appear in the Claude prompt."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    pkg = {"name": "app", "scripts": {"build": "ng build", "test": "vitest run"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")

    mock_claude.complete_structured.return_value = ProjectCommands(
        build=["npm run build"], test=["npx vitest run"], lint=[], reasoning="",
    )
    node = make_detect_commands_node(mock_claude, non_dry)
    node(make_state())
    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    assert "vitest run" in call_kwargs["user_message"]
    assert "ng build" in call_kwargs["user_message"]


def test_detect_commands_empty_on_empty_dir(settings, mock_claude, tmp_path, monkeypatch):
    """When no manifest is found, scripts block should be empty but not crash."""
    non_dry = settings.model_copy(update={"dry_run": False})
    monkeypatch.chdir(tmp_path)
    mock_claude.complete_structured.return_value = ProjectCommands(
        build=[], test=[], lint=[], reasoning="No manifest found",
    )
    node = make_detect_commands_node(mock_claude, non_dry)
    result = node(make_state())
    assert result["setup_commands"] == []
    assert result["build_commands"] == []
    assert result["test_commands"] == []
    assert result["lint_commands"] == []
    assert result["e2e_commands"] == []


def test_project_commands_schema_defaults():
    """ProjectCommands should have sensible defaults."""
    cmd = ProjectCommands()
    assert cmd.setup == []
    assert cmd.build == []
    assert cmd.test == []
    assert cmd.lint == []
    assert cmd.e2e == []
    assert cmd.reasoning == ""


def test_detect_commands_returns_e2e_commands(settings, mock_claude):
    """When Claude detects E2E commands, they should be returned separately."""
    non_dry = settings.model_copy(update={"dry_run": False})
    mock_claude.complete_structured.return_value = ProjectCommands(
        build=["npm run build"],
        test=["npx vitest run"],
        lint=["npm run lint"],
        e2e=["npx playwright test"],
        reasoning="React app with Playwright",
    )
    node = make_detect_commands_node(mock_claude, non_dry)
    result = node(make_state(project_context="React (TypeScript)"))
    assert result["e2e_commands"] == ["npx playwright test"]


def test_detect_commands_prompt_includes_setup_category(settings, mock_claude):
    """Prompt should ask Claude to detect setup commands separately."""
    non_dry = settings.model_copy(update={"dry_run": False})
    mock_claude.complete_structured.return_value = ProjectCommands(
        build=[], test=[], lint=[], reasoning="",
    )
    node = make_detect_commands_node(mock_claude, non_dry)
    node(make_state())
    call_kwargs = mock_claude.complete_structured.call_args.kwargs
    prompt = call_kwargs["user_message"]
    assert "**setup**" in prompt
    assert "npm install" in prompt
    assert "dotnet restore" in prompt
