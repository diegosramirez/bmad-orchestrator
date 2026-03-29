from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from bmad_orchestrator.services.claude_agent_service import ClaudeAgentService


class _DummySchema(BaseModel):
    summary: str
    items: list[str]


@pytest.fixture
def agent_service(settings):
    return ClaudeAgentService(settings)


def test_dry_run_returns_placeholder(agent_service):
    """Dry-run should skip the agent call and return an empty result."""
    result = agent_service.run_agent(
        "test prompt", system_prompt="test", agent_id="developer"
    )
    assert result.is_error is False
    assert result.touched_files == []
    assert result.result_text == "[DRY RUN — no agent session]"


def test_dry_run_with_schema_returns_model_construct(agent_service):
    """Dry-run with output_format_schema returns a constructed model instance."""
    result = agent_service.run_agent(
        "test prompt",
        system_prompt="test",
        agent_id="architect",
        output_format_schema=_DummySchema,
    )
    assert isinstance(result.structured_output, _DummySchema)
    assert result.structured_output.summary == "[DRY RUN]"
    assert result.structured_output.items == []


def test_dry_run_does_not_track_usage(agent_service):
    """Dry-run should not add any usage records."""
    agent_service.run_agent("test", system_prompt="test", agent_id="qa")
    assert len(agent_service._usage) == 0


def test_model_for_uses_agent_models_override(settings):
    """Per-agent model overrides should be respected."""
    settings_with_overrides = settings.model_copy(
        update={"agent_models": {"developer": "claude-3-haiku-20240307"}}
    )
    service = ClaudeAgentService(settings_with_overrides)
    assert service._model_for("developer") == "claude-3-haiku-20240307"
    assert service._model_for("qa") == settings.model_name


def test_shared_usage_tracker():
    """When a usage_tracker list is provided, usage records append to it."""
    shared: list[dict] = [{"existing": True}]
    settings = MagicMock(dry_run=True)
    service = ClaudeAgentService(settings, usage_tracker=shared)
    assert service._usage is shared


@pytest.mark.asyncio
async def test_run_async_captures_write_paths(settings):
    """Write/Edit tool uses in AssistantMessage should be captured as touched files."""
    from claude_agent_sdk import AssistantMessage, ResultMessage
    from claude_agent_sdk.types import ToolUseBlock

    non_dry = settings.model_copy(update={"dry_run": False})
    service = ClaudeAgentService(non_dry)

    assistant_msg = AssistantMessage(
        content=[
            ToolUseBlock(id="1", name="Write", input={"file_path": "/tmp/test/foo.ts"}),
            ToolUseBlock(id="2", name="Edit", input={"file_path": "/tmp/test/bar.ts"}),
            ToolUseBlock(id="3", name="Read", input={"file_path": "/tmp/test/baz.ts"}),
            ToolUseBlock(id="4", name="Write", input={"file_path": "/tmp/test/foo.ts"}),
        ],
        model="claude-3-haiku-20240307",
    )
    result_msg = ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=3,
        session_id="test-session",
        usage={"input_tokens": 100, "output_tokens": 50},
        result="Done",
    )

    async def fake_query(prompt, options=None):
        yield assistant_msg
        yield result_msg

    with patch(
        "bmad_orchestrator.services.claude_agent_service.query", fake_query
    ):
        result = await service._run_async(
            prompt="test",
            system_prompt="test",
            agent_id="developer",
            cwd=None,
            allowed_tools=None,
            disallowed_tools=None,
            output_format_schema=None,
            max_turns=5,
        )

    # Write and Edit captured; Read ignored; duplicate Write not added twice
    assert result.touched_files == ["/tmp/test/foo.ts", "/tmp/test/bar.ts"]
    assert result.is_error is False
    assert result.duration_ms == 1000


@pytest.mark.asyncio
async def test_run_async_tracks_usage(settings):
    """Usage records should be appended after a successful session."""
    from claude_agent_sdk import ResultMessage

    non_dry = settings.model_copy(update={"dry_run": False})
    usage_list: list[dict] = []
    service = ClaudeAgentService(non_dry, usage_tracker=usage_list)

    result_msg = ResultMessage(
        subtype="success",
        duration_ms=2500,
        duration_api_ms=2000,
        is_error=False,
        num_turns=5,
        session_id="test-session",
        usage={"input_tokens": 500, "output_tokens": 200},
        result="Done",
    )

    async def fake_query(prompt, options=None):
        yield result_msg

    with patch(
        "bmad_orchestrator.services.claude_agent_service.query", fake_query
    ):
        await service._run_async(
            prompt="test",
            system_prompt="test",
            agent_id="developer",
            cwd=None,
            allowed_tools=None,
            disallowed_tools=None,
            output_format_schema=None,
            max_turns=10,
        )

    assert len(usage_list) == 1
    rec = usage_list[0]
    assert rec["agent_id"] == "developer"
    assert rec["input_tokens"] == 500
    assert rec["output_tokens"] == 200
    assert rec["duration_s"] == 2.5


@pytest.mark.asyncio
async def test_run_async_no_result_message(settings):
    """If no ResultMessage is received, return an error result."""
    from claude_agent_sdk import SystemMessage

    non_dry = settings.model_copy(update={"dry_run": False})
    service = ClaudeAgentService(non_dry)

    async def fake_query(prompt, options=None):
        # Only yield a non-result message
        yield SystemMessage(subtype="init", data={})

    with patch(
        "bmad_orchestrator.services.claude_agent_service.query", fake_query
    ):
        result = await service._run_async(
            prompt="test",
            system_prompt="test",
            agent_id="qa",
            cwd=None,
            allowed_tools=None,
            disallowed_tools=None,
            output_format_schema=None,
            max_turns=5,
        )

    assert result.is_error is True
    assert "without a result" in (result.result_text or "")


@pytest.mark.asyncio
async def test_run_async_structured_output(settings):
    """Structured output from ResultMessage should be passed through."""
    from claude_agent_sdk import ResultMessage

    non_dry = settings.model_copy(update={"dry_run": False})
    service = ClaudeAgentService(non_dry)

    result_msg = ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=2,
        session_id="test-session",
        usage={"input_tokens": 100, "output_tokens": 50},
        structured_output={"summary": "All good", "items": ["no issues"]},
    )

    async def fake_query(prompt, options=None):
        yield result_msg

    with patch(
        "bmad_orchestrator.services.claude_agent_service.query", fake_query
    ):
        result = await service._run_async(
            prompt="test",
            system_prompt="test",
            agent_id="architect",
            cwd=None,
            allowed_tools=["Read", "Glob", "Grep"],
            disallowed_tools=None,
            output_format_schema=_DummySchema,
            max_turns=10,
        )

    assert result.structured_output == {
        "summary": "All good",
        "items": ["no issues"],
    }
