from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from bmad_orchestrator.services.claude_service import ClaudeService, _summarize_model, _truncate


class _SampleSchema(BaseModel):
    value: str = ""


class _RequiredFieldsSchema(BaseModel):
    title: str
    count: int
    active: bool


def _make_mock_usage(input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def _make_text_response(text: str = "hello") -> MagicMock:
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text=text)]
    mock_response.usage = _make_mock_usage()
    return mock_response


def _make_tool_response(tool_input: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = tool_input
    mock_response = MagicMock()
    mock_response.content = [tool_block]
    mock_response.usage = _make_mock_usage()
    return mock_response


# ── _truncate ────────────────────────────────────────────────────────────────

def test_truncate_short_text():
    assert _truncate("hello", 10) == "hello"


def test_truncate_long_text():
    assert _truncate("a" * 200, 50) == "a" * 50 + "..."


def test_truncate_exact_length():
    assert _truncate("12345", 5) == "12345"


# ── _summarize_model ─────────────────────────────────────────────────────────

def test_summarize_model_with_string_fields():
    model = _SampleSchema(value="test")
    summary = _summarize_model(model)
    assert "_SampleSchema(" in summary
    assert "value='test'" in summary


def test_summarize_model_with_list_fields():

    class _ListSchema(BaseModel):
        items: list[str] = []

    model = _ListSchema(items=["a", "b", "c"])
    summary = _summarize_model(model)
    assert "[3 items]" in summary


def test_summarize_model_truncates_long_strings():
    model = _SampleSchema(value="x" * 100)
    summary = _summarize_model(model)
    assert "..." in summary


# ── dry run paths ────────────────────────────────────────────────────────────

def test_complete_dry_run_skips_api(settings):
    svc = ClaudeService(settings)  # settings.dry_run = True
    result = svc.complete("sys", "user msg")
    assert "DRY RUN" in result


def test_complete_structured_dry_run_returns_default(settings):
    svc = ClaudeService(settings)
    result = svc.complete_structured("sys", "user", _SampleSchema)
    assert isinstance(result, _SampleSchema)


def test_complete_structured_dry_run_handles_required_fields(settings):
    svc = ClaudeService(settings)
    result = svc.complete_structured("sys", "user", _RequiredFieldsSchema)
    assert isinstance(result, _RequiredFieldsSchema)
    assert result.title == "[DRY RUN]"
    assert result.count == 0
    assert result.active is False


def test_classify_returns_first_option_on_dry_run(settings):
    svc = ClaudeService(settings)
    with patch.object(svc, "complete", return_value="[DRY RUN — no Claude call made]"):
        result = svc.classify("sys", "Which?", ["option_a", "option_b"])
    # With dry run text, neither option matches exactly; falls back to first
    assert result == "option_a"


# ── live API paths ───────────────────────────────────────────────────────────

def test_complete_calls_anthropic_client(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    with patch.object(svc._client.messages, "create", return_value=_make_text_response("hello")):
        result = svc.complete("system", "user message")

    assert result == "hello"


def test_complete_raises_on_non_text_content(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="image")]

    with patch.object(svc._client.messages, "create", return_value=mock_response):
        with pytest.raises(ValueError, match="Unexpected response type"):
            svc.complete("system", "user message")


def test_complete_structured_real_path(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    with patch.object(svc._client.messages, "create",
                      return_value=_make_tool_response({"value": "extracted"})):
        result = svc.complete_structured("sys", "user", _SampleSchema)

    assert result.value == "extracted"


def test_complete_structured_raises_when_no_tool_use_block(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    text_block = MagicMock()
    text_block.type = "text"
    mock_response = MagicMock()
    mock_response.content = [text_block]

    with patch.object(svc._client.messages, "create", return_value=mock_response):
        with pytest.raises(ValueError, match="tool_use"):
            svc.complete_structured("sys", "user", _SampleSchema)


def test_complete_structured_raises_on_truncation(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    mock_response = _make_tool_response({"value": "partial"})
    mock_response.stop_reason = "max_tokens"
    mock_response.usage.output_tokens = 4096

    with patch.object(svc._client.messages, "create", return_value=mock_response):
        with pytest.raises(ValueError, match="truncated"):
            svc.complete_structured("sys", "user", _SampleSchema, max_tokens=4096)


def test_classify_falls_back_to_first_option_when_no_match(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)
    with patch.object(svc, "complete", return_value="I have no idea"):
        result = svc.classify("sys", "Which one?", ["option_a", "option_b"])
    assert result == "option_a"


# ── agent_id logging ─────────────────────────────────────────────────────────

def test_complete_logs_agent_name(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    with patch.object(svc._client.messages, "create", return_value=_make_text_response("ok")):
        with patch("bmad_orchestrator.services.claude_service.logger") as mock_logger:
            svc.complete("sys", "user msg", agent_id="pm")

    # Check that the request log includes the resolved agent name
    request_call = mock_logger.info.call_args_list[0]
    assert request_call[0][0] == "claude_request"
    assert request_call[1]["agent"] == "Alex (PM)"

    # Check that the response log also has the agent
    response_call = mock_logger.info.call_args_list[1]
    assert response_call[0][0] == "claude_response"
    assert response_call[1]["agent"] == "Alex (PM)"


def test_complete_structured_logs_agent_name(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    with patch.object(svc._client.messages, "create",
                      return_value=_make_tool_response({"value": "test"})):
        with patch("bmad_orchestrator.services.claude_service.logger") as mock_logger:
            svc.complete_structured("sys", "user", _SampleSchema, agent_id="architect")

    request_call = mock_logger.info.call_args_list[0]
    assert request_call[1]["agent"] == "Winston (Architect)"


def test_classify_passes_agent_id_to_complete(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    with patch.object(svc, "complete", return_value="option_a") as mock_complete:
        svc.classify("sys", "Which?", ["option_a", "option_b"], agent_id="qa")

    assert mock_complete.call_args[1]["agent_id"] == "qa"


def test_unknown_agent_id_uses_raw_string(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    with patch.object(svc._client.messages, "create", return_value=_make_text_response("ok")):
        with patch("bmad_orchestrator.services.claude_service.logger") as mock_logger:
            svc.complete("sys", "msg", agent_id="custom_agent")

    request_call = mock_logger.info.call_args_list[0]
    assert request_call[1]["agent"] == "custom_agent"


def test_complete_logs_token_usage(settings):
    live_settings = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live_settings)

    resp = _make_text_response("result")
    resp.usage.input_tokens = 500
    resp.usage.output_tokens = 42

    with patch.object(svc._client.messages, "create", return_value=resp):
        with patch("bmad_orchestrator.services.claude_service.logger") as mock_logger:
            svc.complete("sys", "msg", agent_id="pm")

    response_call = mock_logger.info.call_args_list[1]
    assert response_call[1]["tokens_in"] == 500
    assert response_call[1]["tokens_out"] == 42
    assert "duration_s" in response_call[1]


# ── usage tracking ──────────────────────────────────────────────────────────

def test_usage_accumulates_on_complete(settings):
    live = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live)
    resp = _make_text_response("ok")
    resp.usage.input_tokens = 200
    resp.usage.output_tokens = 80

    with patch.object(svc._client.messages, "create", return_value=resp):
        svc.complete("sys", "msg", agent_id="developer")

    assert len(svc._usage) == 1
    assert svc._usage[0]["input_tokens"] == 200
    assert svc._usage[0]["output_tokens"] == 80
    assert svc._usage[0]["agent_id"] == "developer"


def test_usage_accumulates_on_complete_structured(settings):
    live = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live)
    resp = _make_tool_response({"value": "x"})
    resp.usage.input_tokens = 300
    resp.usage.output_tokens = 120

    with patch.object(svc._client.messages, "create", return_value=resp):
        svc.complete_structured("sys", "msg", _SampleSchema, agent_id="qa")

    assert len(svc._usage) == 1
    assert svc._usage[0]["input_tokens"] == 300
    assert svc._usage[0]["agent_id"] == "qa"


def test_dry_run_does_not_accumulate_usage(settings):
    svc = ClaudeService(settings)  # dry_run=True
    svc.complete("sys", "msg")
    svc.complete_structured("sys", "msg", _SampleSchema)
    assert svc._usage == []


def test_get_usage_report_groups_by_agent(settings):
    live = settings.model_copy(update={"dry_run": False})
    svc = ClaudeService(live)
    text_resp = _make_text_response("ok")
    text_resp.usage.input_tokens = 100
    text_resp.usage.output_tokens = 50
    tool_resp = _make_tool_response({"value": "v"})
    tool_resp.usage.input_tokens = 200
    tool_resp.usage.output_tokens = 80

    with patch.object(
        svc._client.messages, "create", return_value=text_resp,
    ):
        svc.complete("sys", "msg", agent_id="developer")
        svc.complete("sys", "msg", agent_id="developer")

    with patch.object(
        svc._client.messages, "create", return_value=tool_resp,
    ):
        svc.complete_structured("sys", "m", _SampleSchema, agent_id="qa")

    report = svc.get_usage_report()
    assert report["total_calls"] == 3
    assert report["total_input"] == 400  # 100+100+200
    assert report["total_output"] == 180  # 50+50+80
    assert report["total"] == 580
    assert report["model"] == live.model_name

    dev_row = next(r for r in report["rows"] if r["agent"] == "Amelia (Developer)")
    assert dev_row["calls"] == 2
    assert dev_row["input_tokens"] == 200
    qa_row = next(r for r in report["rows"] if r["agent"] == "Quinn (QA)")
    assert qa_row["calls"] == 1
    assert report["models_mixed"] is False


def test_model_for_uses_agent_models_override(settings):
    live = settings.model_copy(update={
        "dry_run": False,
        "agent_models": {"developer": "claude-3-haiku-20240307"},
    })
    svc = ClaudeService(live)
    assert svc._model_for("developer") == "claude-3-haiku-20240307"
    assert svc._model_for("qa") == live.model_name  # fallback


def test_agent_model_override_used_in_api_call(settings):
    live = settings.model_copy(update={
        "dry_run": False,
        "agent_models": {"developer": "claude-3-haiku-20240307"},
    })
    svc = ClaudeService(live)
    resp = _make_text_response("ok")

    with patch.object(
        svc._client.messages, "create", return_value=resp,
    ) as mock_create:
        svc.complete("sys", "msg", agent_id="developer")

    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["model"] == "claude-3-haiku-20240307"


def test_usage_report_shows_mixed_models(settings):
    live = settings.model_copy(update={
        "dry_run": False,
        "agent_models": {"qa": "claude-3-haiku-20240307"},
    })
    svc = ClaudeService(live)
    text_resp = _make_text_response("ok")
    tool_resp = _make_tool_response({"value": "v"})

    with patch.object(
        svc._client.messages, "create", return_value=text_resp,
    ):
        svc.complete("sys", "msg", agent_id="developer")

    with patch.object(
        svc._client.messages, "create", return_value=tool_resp,
    ):
        svc.complete_structured(
            "sys", "m", _SampleSchema, agent_id="qa",
        )

    report = svc.get_usage_report()
    assert report["models_mixed"] is True
    qa_row = next(
        r for r in report["rows"] if r["agent"] == "Quinn (QA)"
    )
    assert qa_row["model"] == "claude-3-haiku-20240307"
