from __future__ import annotations

from bmad_orchestrator.cli import _format_agent_timeline, _parse_kv, _relative_time


class TestParseKv:
    def test_single_quoted_values(self) -> None:
        kv = _parse_kv("agent='Alex (PM)' method=complete_structured")
        assert kv["agent"] == "Alex (PM)"
        assert kv["method"] == "complete_structured"

    def test_double_quoted_values(self) -> None:
        kv = _parse_kv('response="some text here"')
        assert kv["response"] == "some text here"

    def test_unquoted_values(self) -> None:
        kv = _parse_kv("tokens_in=1180 tokens_out=200 duration_s=6.74")
        assert kv["tokens_in"] == "1180"
        assert kv["tokens_out"] == "200"
        assert kv["duration_s"] == "6.74"


class TestRelativeTime:
    def test_zero_offset(self) -> None:
        assert _relative_time("13:39:21", "13:39:21") == "+0:00"

    def test_seconds_offset(self) -> None:
        assert _relative_time("13:39:28", "13:39:21") == "+0:07"

    def test_minutes_offset(self) -> None:
        assert _relative_time("13:41:21", "13:39:21") == "+2:00"

    def test_mixed_offset(self) -> None:
        assert _relative_time("13:44:53", "13:39:21") == "+5:32"


class TestFormatAgentTimeline:
    SAMPLE_LOG = (
        "2026-03-16T13:39:21.809996Z [info     ] claude_request"
        "                 agent='Alex (PM)' method=complete_structured"
        " schema=EpicRoutingDecision\n"
        "2026-03-16T13:39:28.546460Z [info     ] claude_response"
        "                agent='Alex (PM)' duration_s=6.74"
        " method=complete_structured tokens_in=1180 tokens_out=200\n"
        "2026-03-16T13:39:28.877230Z [debug    ] slack_api_ok"
        "                   method=chat.postMessage\n"
        "2026-03-16T13:39:58.638310Z [info     ] epic_created"
        "                   key=SAM1-175\n"
        "2026-03-16T13:39:58.899042Z [info     ] claude_request"
        "                 agent='Bob (Scrum Master)'"
        " method=complete_structured schema=StoryDraft\n"
    )

    def test_groups_by_agent(self) -> None:
        result = _format_agent_timeline(self.SAMPLE_LOG)
        assert "### Alex (PM)" in result
        assert "### Bob (Scrum Master)" in result
        assert "### System" in result

    def test_contains_timeline_header(self) -> None:
        result = _format_agent_timeline(self.SAMPLE_LOG)
        assert "## Agent Timeline" in result

    def test_contains_table_headers(self) -> None:
        result = _format_agent_timeline(self.SAMPLE_LOG)
        assert "| Time | Event | Details |" in result

    def test_claude_request_shows_method_and_schema(self) -> None:
        result = _format_agent_timeline(self.SAMPLE_LOG)
        assert "method=complete_structured" in result
        assert "schema=EpicRoutingDecision" in result

    def test_claude_response_shows_tokens(self) -> None:
        result = _format_agent_timeline(self.SAMPLE_LOG)
        assert "tokens=1180→200" in result
        assert "duration=6.74s" in result

    def test_relative_time_in_output(self) -> None:
        result = _format_agent_timeline(self.SAMPLE_LOG)
        assert "(+0:00)" in result
        assert "(+0:07)" in result

    def test_skips_claude_request_full(self) -> None:
        log = (
            "2026-03-16T13:39:21.000000Z [debug    ] claude_request_full"
            "            agent='Alex (PM)' prompt='very long prompt...'\n"
        )
        result = _format_agent_timeline(log)
        assert "claude_request_full" not in result

    def test_agent_tool_use_shows_tool(self) -> None:
        log = (
            "2026-03-16T13:45:04.583685Z [info     ] agent_tool_use"
            "                 agent='Amelia (Developer)'"
            " detail='mkdir -p /some/path' tool=Bash turn=5\n"
        )
        result = _format_agent_timeline(log)
        assert "tool=Bash" in result
        assert "mkdir -p /some/path" in result

    def test_empty_input(self) -> None:
        assert _format_agent_timeline("") == ""
        assert _format_agent_timeline("not a log line\n") == ""

    def test_pipe_chars_escaped(self) -> None:
        log = (
            "2026-03-16T13:39:21.000000Z [info     ] some_event"
            "                     detail='a|b'\n"
        )
        result = _format_agent_timeline(log)
        assert "a\\|b" in result
