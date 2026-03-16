from __future__ import annotations

from unittest.mock import MagicMock

from bmad_orchestrator.config import Settings
from bmad_orchestrator.graph import _make_verbose_callback


class TestMakeVerboseCallback:
    """Tests for _make_verbose_callback in graph.py."""

    def _make_settings(self, **overrides: object) -> Settings:
        base = {
            "anthropic_api_key": "sk-test",
            "dummy_jira": True,
            "dummy_github": True,
            "slack_notify": True,
            "slack_bot_token": "xoxb-test",
            "slack_channel": "#test",
            "slack_verbose": True,
        }
        base.update(overrides)
        return Settings(**base)  # type: ignore[arg-type]

    def test_posts_to_thread_when_verbose(self) -> None:
        slack = MagicMock()
        settings = self._make_settings()
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_called_once_with("ts123", "hello")

    def test_noop_when_verbose_disabled(self) -> None:
        slack = MagicMock()
        settings = self._make_settings(slack_verbose=False)
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_not_called()

    def test_noop_when_slack_notify_disabled(self) -> None:
        slack = MagicMock()
        settings = self._make_settings(
            slack_notify=False, slack_bot_token=None, slack_channel=None,
        )
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_not_called()

    def test_noop_when_no_thread_ts(self) -> None:
        slack = MagicMock()
        settings = self._make_settings()
        holder: list[str | None] = [None]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_not_called()

    def test_swallows_exceptions(self) -> None:
        slack = MagicMock()
        slack.post_thread_reply.side_effect = RuntimeError("Slack down")
        settings = self._make_settings()
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        # Should NOT raise
        cb("hello")
        slack.post_thread_reply.assert_called_once()

    def test_holder_updates_reflected(self) -> None:
        """Callback reads from the mutable holder, so later updates take effect."""
        slack = MagicMock()
        settings = self._make_settings()
        holder: list[str | None] = [None]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("first")  # holder is None → no call
        slack.post_thread_reply.assert_not_called()

        holder[0] = "ts456"
        cb("second")
        slack.post_thread_reply.assert_called_once_with("ts456", "second")
