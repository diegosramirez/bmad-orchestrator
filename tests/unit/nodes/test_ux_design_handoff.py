from __future__ import annotations

from pydantic import SecretStr

from bmad_orchestrator.nodes.ux_design_handoff import (
    ComponentSpec,
    UxHandoff,
    format_handoff_markdown,
    make_ux_design_handoff_node,
)
from bmad_orchestrator.services.claude_agent_service import AgentResult
from tests.conftest import make_state


def _figma_settings(settings):
    return settings.model_copy(
        update={
            "figma_mcp_enabled": True,
            "figma_mcp_token": SecretStr("figd_test"),
        }
    )


def test_node_skips_when_mcp_disabled(settings, mock_agent_service):
    node = make_ux_design_handoff_node(mock_agent_service, settings)
    result = node(make_state(figma_url="https://www.figma.com/design/abc/X"))
    assert "ux_handoff" not in result
    mock_agent_service.run_agent.assert_not_called()
    assert result["execution_log"][0]["message"].startswith("Skipped")


def test_node_skips_when_no_figma_url(settings, mock_agent_service):
    figma_settings = _figma_settings(settings)
    node = make_ux_design_handoff_node(mock_agent_service, figma_settings)
    result = node(make_state(figma_url=None))
    assert "ux_handoff" not in result
    mock_agent_service.run_agent.assert_not_called()


def test_node_produces_markdown_handoff(settings, mock_agent_service):
    handoff = UxHandoff(
        summary="Primary login screen",
        components=[
            ComponentSpec(
                name="LoginForm",
                description="Email + password inputs and submit button",
                props=["onSubmit", "loading"],
            )
        ],
        design_tokens=["color.primary=#2F5CFF", "spacing.md=16px"],
        accessibility_notes=["Labels tied to inputs via htmlFor"],
        suggested_file_paths=["src/app/login/login.component.ts"],
    )
    mock_agent_service.run_agent.return_value = AgentResult(
        structured_output=handoff,
        result_text="ok",
    )
    node = make_ux_design_handoff_node(mock_agent_service, _figma_settings(settings))
    result = node(
        make_state(
            figma_url="https://www.figma.com/design/abc/Login",
            story_content="Build login UI",
            acceptance_criteria=["User can sign in"],
        )
    )
    assert "ux_handoff" in result
    md = result["ux_handoff"]
    assert "UX design handoff" in md
    assert "LoginForm" in md
    assert "color.primary=#2F5CFF" in md
    assert "src/app/login/login.component.ts" in md

    kwargs = mock_agent_service.run_agent.call_args.kwargs
    assert kwargs["mcp_servers"] == {
        "figma": {
            "type": "http",
            "url": "https://mcp.figma.com/mcp",
            "headers": {"Authorization": "Bearer figd_test"},
        }
    }
    assert kwargs["agent_id"] == "designer"


def test_node_handles_agent_error(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=True,
        result_text="boom",
    )
    node = make_ux_design_handoff_node(mock_agent_service, _figma_settings(settings))
    result = node(make_state(figma_url="https://www.figma.com/design/abc/X"))
    assert "ux_handoff" not in result
    assert "UX handoff failed" in result["execution_log"][0]["message"]


def test_node_handles_missing_structured_output(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        is_error=False,
        structured_output=None,
        result_text="no structure",
    )
    node = make_ux_design_handoff_node(mock_agent_service, _figma_settings(settings))
    result = node(make_state(figma_url="https://www.figma.com/design/abc/X"))
    assert "ux_handoff" not in result
    assert "UX handoff failed" in result["execution_log"][0]["message"]


def test_node_coerces_dict_structured_output(settings, mock_agent_service):
    mock_agent_service.run_agent.return_value = AgentResult(
        structured_output={
            "summary": "Dashboard",
            "components": [],
            "design_tokens": [],
            "accessibility_notes": [],
            "suggested_file_paths": [],
        },
        result_text="ok",
    )
    node = make_ux_design_handoff_node(mock_agent_service, _figma_settings(settings))
    result = node(make_state(figma_url="https://www.figma.com/design/abc/X"))
    assert "Dashboard" in result["ux_handoff"]


def test_format_handoff_markdown_omits_empty_sections():
    handoff = UxHandoff(summary="Just the summary")
    md = format_handoff_markdown(handoff)
    assert "Just the summary" in md
    assert "### Components" not in md
    assert "### Design tokens" not in md
    assert "### Accessibility" not in md
    assert "### Suggested file paths" not in md
